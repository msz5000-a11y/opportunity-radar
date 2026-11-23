"""Colectores del pulso: mercados, anuncios de exchanges, DeFi, bolsa de EE. UU., noticias, redes y ayudas públicas.

Cada colector recibe el contexto y devuelve una lista de elementos ya normalizados (ver `item`). Si falla,
lanza una excepción: el motor la registra como fuente caída y sigue con las demás. Todas las fuentes son
gratuitas; las que necesitan clave (Finnhub, Massive, GitHub) se saltan si falta.
"""
from __future__ import annotations

import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse
from zoneinfo import ZoneInfo

import requests

from . import pulse_rules as R

UA = "OpportunityRadarAI/3.0 (+https://github.com/msz5000-a11y/opportunity-radar; personal research)"
CG = "https://api.coingecko.com/api/v3"
FH = "https://finnhub.io/api/v1"
NY = ZoneInfo("America/New_York")

_local = threading.local()
_lock = threading.Lock()
_next_slot: dict[str, float] = {}
HOST_GAP = {"finnhub.io": 1.05, "api.coingecko.com": 2.5, "news.google.com": 1.5, "www.infosubvenciones.es": 1.0,
            "apewisdom.io": 1.0, "api.massive.com": 13.0, "api.polygon.io": 13.0}


class SourceError(Exception):
    pass


def _session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"})
        _local.s = s
    return s


def _wait_turn(host: str):
    gap = HOST_GAP.get(host, 0.35)
    with _lock:
        now = time.time()
        slot = max(now, _next_slot.get(host, 0))
        _next_slot[host] = slot + gap
    if slot > now:
        time.sleep(slot - now)


def fetch(url: str, *, params=None, headers=None, timeout=20, etags: dict | None = None) -> requests.Response | None:
    """GET con turno por servidor. Con `etags` hace petición condicional: devuelve None si no hay cambios (304)."""
    host = urlparse(url).netloc
    hdr = dict(headers or {})
    key = url if not params else url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "token")
    if etags is not None and key in etags:
        e = etags[key]
        if e.get("e"):
            hdr["If-None-Match"] = e["e"]
        if e.get("m"):
            hdr["If-Modified-Since"] = e["m"]
    for attempt in range(2):
        _wait_turn(host)
        try:
            r = _session().get(url, params=params, headers=hdr, timeout=timeout)
        except requests.RequestException as ex:
            if attempt:
                raise SourceError(str(ex)[:160])
            time.sleep(1.5)
            continue
        if r.status_code == 304:
            return None
        if r.status_code == 429 or r.status_code >= 500:
            if attempt:
                raise SourceError(f"HTTP {r.status_code}")
            time.sleep(3)
            continue
        if r.status_code >= 400:
            raise SourceError(f"HTTP {r.status_code}")
        if etags is not None and (r.headers.get("ETag") or r.headers.get("Last-Modified")):
            etags[key] = {"e": r.headers.get("ETag"), "m": r.headers.get("Last-Modified")}
        return r
    raise SourceError("sin respuesta")


def get_json(url, **kw):
    r = fetch(url, **kw)
    return None if r is None else r.json()


# ------------------------------------------------------------------ utilidades
def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_date(s) -> datetime | None:
    if not s:
        return None
    if isinstance(s, (int, float)):
        v = float(s)
        return datetime.fromtimestamp(v / 1000 if v > 1e12 else v, timezone.utc)
    s = str(s).strip()
    try:
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1) if "T" not in s and " " in s else s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def item(id, cat, kind, src, *, title, url="", es=None, en=None, why=None, act=None, why_en=None, act_en=None, sum=None,
         sym=None, m=None, s=50, opp=2, risk="medio", tags=(), also=(), pub=None, srcs=None) -> dict:
    it = {"id": id, "cat": cat, "kind": kind, "src": src, "title": R.clean(title)[:220], "url": url or "", "s": int(s), "opp": int(opp),
          "risk": risk}
    for k, v in (("es", es), ("en", en), ("why", why), ("act", act), ("why_en", why_en), ("act_en", act_en), ("sym", sym), ("m", m),
                 ("pub", pub)):
        if v:
            it[k] = v
    if sum:
        it["sum"] = R.clean(sum)[:300]
    if tags:
        it["tags"] = list(dict.fromkeys(tags))
    if also:
        it["also"] = [c for c in dict.fromkeys(also) if c != cat]
    if srcs:
        it["srcs"] = srcs
    return it


class Ctx:
    """Lo que comparten los colectores durante una ejecución."""

    def __init__(self, now: datetime, state: dict, cfg: dict, fund: dict | None = None, watch: list[str] | None = None):
        self.now = now
        self.today = now.astimezone(ZoneInfo("Europe/Madrid")).date().isoformat()
        self.state = state
        self.cfg = cfg
        self.fund = fund or {}
        self.watch = watch or []
        self.share: dict = {}
        self.etags = state.setdefault("etags", {})
        self.region = (cfg.get("profile") or {}).get("region", "es")

    def mem(self, name: str, default=None):
        return self.state.setdefault("mem", {}).setdefault(name, default if default is not None else {})

    def setmem(self, name: str, value):
        self.state.setdefault("mem", {})[name] = value


# ------------------------------------------------------------------ cripto: mercado
def c_cg_markets(ctx: Ctx) -> list[dict]:
    data = get_json(f"{CG}/coins/markets", params={"vs_currency": "eur", "order": "market_cap_desc", "per_page": 250, "page": 1,
                                                   "price_change_percentage": "1h,24h,7d"})
    if not isinstance(data, list):
        raise SourceError("respuesta inesperada")
    ctx.share["cg"] = {c["id"]: c for c in data}
    trending = set(ctx.mem("cg_trending_ids", []))
    out = []
    for c in data:
        sym, name = (c.get("symbol") or "").upper(), c.get("name") or ""
        if not R.is_plain_coin(sym, name):
            continue
        mcap, vol = c.get("market_cap") or 0, c.get("total_volume") or 0
        if mcap < 1e8 or vol < 5e6:
            continue
        ch1 = c.get("price_change_percentage_1h_in_currency")
        ch24 = c.get("price_change_percentage_24h_in_currency", c.get("price_change_percentage_24h"))
        ch7 = c.get("price_change_percentage_7d_in_currency")
        vr = vol / mcap if mcap else None
        m = {"price": c.get("current_price"), "cur": "EUR", "ch1h": _r(ch1), "ch24h": _r(ch24), "ch7d": _r(ch7), "vol": vol, "mcap": mcap,
             "rank": c.get("market_cap_rank")}
        url = f"https://www.coingecko.com/es/monedas/{c['id']}"
        hot = c["id"] in trending
        if ch24 is not None and abs(ch24) >= 10:
            up = ch24 > 0
            b = R.move_bucket(ch24)
            s = R.score_move(ch24, vr, mcap, 10) + (6 if hot else 0)
            why = (f"Movimiento fuerte con {R.fmt_eur(vol)} de volumen en 24 h ({vr:.0%} de su capitalización)." if vr else "Movimiento fuerte.")
            why_en = f"Strong move with {R.fmt_eur(vol, 'en')} traded in 24h."
            if hot:
                why += " Además está entre las más buscadas en CoinGecko."
                why_en += " It is also trending on CoinGecko searches."
            out.append(item(f"mv:{c['id']}:{ctx.today}:{'u' if up else 'd'}{b}", "cripto", "move", "CoinGecko",
                            title=f"{name} ({sym}) {'sube' if up else 'cae'} un {R.fmt_pct(abs(ch24))[1:]} en 24 h",
                            es=f"{name} ({sym}) {'sube' if up else 'cae'} un {R.fmt_pct(abs(ch24))[1:]} en 24 h",
                            en=f"{name} ({sym}) {'up' if up else 'down'} {abs(ch24):.1f}% in 24h",
                            why=why, why_en=why_en,
                            act=("Busca la noticia que lo explica antes de entrar. Si compras, que sea poco y con stop: tras subidas así son normales recortes del 10-20 %."
                                 if up else "No compres a ciegas «porque está barato»: espera a que se estabilice y comprueba si hay un problema (hackeo, desbloqueo de tokens, regulación)."),
                            act_en=("Find the news behind it before buying. Size small and use a stop; 10-20% pullbacks are normal after such moves."
                                    if up else "Don't buy blindly because it's cheaper: wait for it to stabilise and check for a real problem (hack, unlock, regulation)."),
                            sym=sym, m=m, s=s, opp=2, risk="muy_alto" if mcap < 3e8 else "alto", tags=["subida" if up else "caida"], url=url))
        elif ch1 is not None and abs(ch1) >= 4 and mcap >= 3e8:
            up = ch1 > 0
            b = R.move_bucket(ch1, (4, 8, 12, 20))
            s = R.score_move(ch1 * 2.2, vr, mcap, 10) + (5 if hot else 0)
            out.append(item(f"m1:{c['id']}:{ctx.today}:{'u' if up else 'd'}{b}", "cripto", "move", "CoinGecko",
                            title=f"{name} ({sym}) {'se dispara' if up else 'se desploma'} un {R.fmt_pct(abs(ch1))[1:]} en la última hora",
                            es=f"{name} ({sym}) {'se dispara' if up else 'se desploma'} un {R.fmt_pct(abs(ch1))[1:]} en la última hora",
                            en=f"{name} ({sym}) {'spikes' if up else 'drops'} {abs(ch1):.1f}% in the last hour",
                            why="Movimiento brusco en muy poco tiempo: suele haber una noticia o una orden grande detrás.",
                            why_en="Sharp move in a short time: usually news or a large order behind it.",
                            act="Mira Noticias y Redes en esta categoría para ver la causa. No entres solo por el impulso.",
                            act_en="Check News and Social for the cause. Don't chase momentum alone.",
                            sym=sym, m=m, s=s, opp=2, risk="alto", tags=["subida" if up else "caida"], url=url))
    return out


def _r(x, n=2):
    return round(x, n) if isinstance(x, (int, float)) else None


def c_cg_trending(ctx: Ctx) -> list[dict]:
    data = get_json(f"{CG}/search/trending") or {}
    out, ids = [], []
    for i, c in enumerate((data.get("coins") or [])[:15]):
        it = c.get("item") or {}
        cid, sym, name = it.get("id"), (it.get("symbol") or "").upper(), it.get("name") or ""
        if not cid or not R.is_plain_coin(sym, name):
            continue
        ids.append(cid)
        if (it.get("market_cap_rank") or 999) <= 10:
            continue  # BTC, ETH… siempre están: no aporta
        d = it.get("data") or {}
        ch = (d.get("price_change_percentage_24h") or {}).get("eur")
        rank = it.get("market_cap_rank")
        s = 40 + max(0, 15 - i) * 1.4 + (8 if ch is not None and abs(ch) >= 10 else 0)
        if rank and rank <= 100:
            s += 4
        if rank is None or rank > 600:
            s -= 6
        out.append(item(f"tr:cg:{cid}:{ctx.today}", "cripto", "trend", "CoinGecko",
                        title=f"{name} ({sym}) entre las más buscadas en CoinGecko (#{i + 1})",
                        es=f"{name} ({sym}) entre las más buscadas en CoinGecko (#{i + 1})",
                        en=f"{name} ({sym}) trending on CoinGecko searches (#{i + 1})",
                        why=("Mucha gente la está buscando ahora" + (f"; {R.fmt_pct(ch)} en 24 h." if ch is not None else ".")
                             + (" Es una moneda pequeña: riesgo muy alto." if not rank or rank > 300 else "")),
                        why_en="Lots of people are searching for it right now" + (f"; {ch:+.1f}% in 24h." if ch is not None else "."),
                        act="El interés en búsquedas suele acompañar a movimientos fuertes. Compara con el precio antes de actuar.",
                        act_en="Search interest often comes with strong moves. Compare with price action before acting.",
                        sym=sym, m={"rank": rank, "ch24h": _r(ch), "price": d.get("price"), "cur": "USD"}, s=int(s),
                        opp=2 if i < 5 else 1, risk="muy_alto" if not rank or rank > 300 else "alto", tags=["tendencia"],
                        url=f"https://www.coingecko.com/es/monedas/{cid}"))
    ctx.setmem("cg_trending_ids", ids)
    for cat in (data.get("categories") or [])[:5]:
        name = cat.get("name")
        ch = (cat.get("data") or {}).get("market_cap_change_percentage_24h", {}).get("usd")
        if not name:
            continue
        out.append(item(f"tc:cg:{R.h(name)}:{ctx.today}", "cripto", "trend", "CoinGecko",
                        title=f"Sector en tendencia: {name}", es=f"Sector cripto en tendencia: {name}", en=f"Trending crypto sector: {name}",
                        why="Las narrativas (IA, RWA, memes, juegos…) concentran el dinero durante semanas." + (f" Capitalización del sector {R.fmt_pct(ch)} en 24 h." if ch is not None else ""),
                        why_en="Narratives concentrate money for weeks." + (f" Sector market cap {ch:+.1f}% in 24h." if ch is not None else ""),
                        act="Si te interesa el sector, mira sus monedas más grandes y líquidas en lugar de las diminutas.",
                        act_en="If you like the theme, look at its larger, liquid coins rather than tiny ones.",
                        m={"ch24h": _r(ch)}, s=46, opp=1, risk="alto", tags=["narrativa"],
                        url=f"https://www.coingecko.com/es/categorias/{cat.get('slug') or ''}"))
    return out


def c_fng(ctx: Ctx) -> list[dict]:
    d = (get_json("https://api.alternative.me/fng/?limit=2") or {}).get("data") or []
    if not d:
        raise SourceError("sin datos")
    v, label = int(d[0]["value"]), d[0].get("value_classification", "")
    ctx.share["fng"] = {"v": v, "label": label}
    zone = "fear" if v <= 20 else "greed" if v >= 80 else None
    if not zone:
        return []
    es_label = "miedo extremo" if zone == "fear" else "codicia extrema"
    return [item(f"fg:{ctx.today}:{zone}", "cripto", "context", "Alternative.me",
                 title=f"Índice de miedo y codicia cripto en {v}/100: {es_label}", es=f"Índice de miedo y codicia cripto en {v}/100: {es_label}",
                 en=f"Crypto Fear & Greed index at {v}/100: {label}",
                 why=("Históricamente, el miedo extremo ha coincidido con buenas zonas de compra a largo plazo, aunque puede durar semanas."
                      if zone == "fear" else "La codicia extrema suele preceder a correcciones: buen momento para recoger beneficios, no para perseguir."),
                 why_en=("Extreme fear has historically lined up with good long-term entry zones, though it can last weeks."
                         if zone == "fear" else "Extreme greed often precedes pullbacks: a time to take profits, not chase."),
                 act=("Si inviertes a largo plazo, considera compras escalonadas (DCA) en BTC/ETH en vez de entrar de golpe."
                      if zone == "fear" else "Revisa tus posiciones y fija stops o ventas parciales."),
                 act_en=("For long-term investors, consider staggered buys (DCA) in BTC/ETH rather than all at once."
                         if zone == "fear" else "Review positions; set stops or take partial profits."),
                 m={"fng": v}, s=58, opp=2, risk="medio", tags=["sentimiento"], url="https://alternative.me/crypto/fear-and-greed-index/")]


# ------------------------------------------------------------------ cripto: altas en exchanges
EX_URL = {"coinbase": "https://www.coinbase.com/es/price/{b}", "kraken": "https://www.kraken.com/es/prices/{b}",
          "okx": "https://www.okx.com/es-es/trade-spot/{b}-usdt", "bitget": "https://www.bitget.com/es/spot/{B}USDT",
          "kucoin": "https://www.kucoin.com/es/trade/{B}-USDT"}
EX_NAME = {"coinbase": "Coinbase", "kraken": "Kraken", "okx": "OKX", "bitget": "Bitget", "kucoin": "KuCoin"}
EX_SCORE = {"coinbase": 80, "kraken": 76, "okx": 68, "kucoin": 60, "bitget": 58}
KRAKEN_ALIAS = {"XBT": "BTC", "XDG": "DOGE"}


def _bases(ex: str) -> set[str]:
    if ex == "coinbase":
        d = get_json("https://api.exchange.coinbase.com/products", timeout=25)
        return {p["base_currency"].upper() for p in d if p.get("status") == "online" and not p.get("trading_disabled")}
    if ex == "kraken":
        d = (get_json("https://api.kraken.com/0/public/AssetPairs", timeout=25) or {}).get("result") or {}
        out = set()
        for p in d.values():
            ws = p.get("wsname") or ""
            if "/" in ws:
                b = ws.split("/")[0].upper()
                out.add(KRAKEN_ALIAS.get(b, b))
        return out
    if ex == "okx":
        d = (get_json("https://www.okx.com/api/v5/public/instruments", params={"instType": "SPOT"}, timeout=25) or {}).get("data") or []
        return {x["baseCcy"].upper() for x in d if x.get("state") == "live" and x.get("baseCcy")}
    if ex == "bitget":
        d = (get_json("https://api.bitget.com/api/v2/spot/public/symbols", timeout=25) or {}).get("data") or []
        return {x["baseCoin"].upper() for x in d if x.get("status") == "online" and x.get("baseCoin")}
    if ex == "kucoin":
        d = (get_json("https://api.kucoin.com/api/v2/symbols", timeout=25) or {}).get("data") or []
        return {x["baseCurrency"].upper() for x in d if x.get("enableTrading") and x.get("baseCurrency")}
    raise SourceError("exchange desconocido")


def listing_collector(ex: str):
    def run(ctx: Ctx) -> list[dict]:
        bases = _bases(ex)
        if len(bases) < 20:
            raise SourceError(f"lista sospechosamente corta ({len(bases)})")
        known_all = ctx.mem("listings")
        known = set(known_all.get(ex) or [])
        out = []
        if known and len(bases) >= 0.8 * len(known):
            for b in sorted(bases - known)[:12]:
                cg = next((c for c in (ctx.share.get("cg") or {}).values() if (c.get("symbol") or "").upper() == b), None)
                name = EX_NAME[ex]
                out.append(item(f"ls:{ex}:{b}", "lanzamientos", "listing", name,
                                title=f"{name} añade {b} para operar", es=f"{name} añade {b} para operar",
                                en=f"{name} adds {b} for trading",
                                why=f"Un alta en {name} da acceso a muchos más compradores y suele traer volumen y volatilidad"
                                    + (f" ({cg['name']}, puesto #{cg.get('market_cap_rank')} por capitalización)." if cg else "."),
                                why_en=f"A {name} listing opens the coin to many more buyers and usually brings volume and volatility.",
                                act="No compres en el primer minuto: el precio suele dispararse y luego corregir. Mira la liquidez y espera a que se asiente.",
                                act_en="Don't buy in the first minute: price often spikes then corrects. Check liquidity and let it settle.",
                                sym=b, s=EX_SCORE[ex], opp=3 if ex in ("coinbase", "kraken", "okx") else 2, risk="alto",
                                tags=["listado"], also=["cripto"], url=EX_URL[ex].format(b=b.lower(), B=b)))
        if not known or len(bases) >= 0.8 * len(known):
            known_all[ex] = sorted(bases | known if known else bases)[-4000:]
        return out
    run.__name__ = f"c_list_{ex}"
    return run


def c_binance_ann(ctx: Ctx) -> list[dict]:
    d = get_json("https://www.binance.com/bapi/composite/v1/public/cms/article/list/query",
                 params={"type": 1, "catalogId": 48, "pageNo": 1, "pageSize": 15}, headers=EN) or {}
    cats = (d.get("data") or {}).get("catalogs") or []
    arts = [a for c in cats for a in (c.get("articles") or [])]
    out = []
    for a in arts:
        title, code, rel = a.get("title") or "", a.get("code"), parse_date(a.get("releaseDate"))
        if not code or (rel and ctx.now - rel > timedelta(days=4)):
            continue
        out.append(_exchange_ann("binance", "Binance", title, f"https://www.binance.com/es/support/announcement/{code}", rel, a.get("id") or code))
    return out


def c_okx_ann(ctx: Ctx) -> list[dict]:
    d = get_json("https://www.okx.com/api/v5/support/announcements", params={"annType": "announcements-new-listings"},
                 headers={**EN, "locale": "en-US"}) or {}
    rows = [x for blk in (d.get("data") or []) for x in (blk.get("details") or [])]
    out = []
    for x in rows:
        rel = parse_date(x.get("pTime"))
        if rel and ctx.now - rel > timedelta(days=4):
            continue
        out.append(_exchange_ann("okx", "OKX", x.get("title") or "", x.get("url") or "", rel, R.h(x.get("title"))))
    return out


EN = {"Accept-Language": "en-US,en;q=0.9"}
DERIV = R._rx(R._kw("perpetual", "perpetuals", "futures", "options", "margin", "usds-m", "usdⓢ-m", "usdⓢ-margined", "usd-margined",
                     "coin-margined", "leverage", "contract", "contracts", "pre-market", "premarket", "tradfi"))


def _exchange_ann(ex: str, name: str, title: str, url: str, rel: datetime | None, uid) -> dict:
    t = R.fold(title)
    asset = None
    m = re.search(r"(?:will list|to list|lists|listing of|will add|adds|introducing|launch(?:es)?|support)\s+(.+?)(?:\s+\(|\s+with|\s+on\b|\s+for\b|[!,.]|$)", title, re.I)
    if m:
        asset = m.group(1).strip()[:40]
    sym = None
    m2 = re.search(r"\(([A-Z0-9]{2,12})\)", title) or (re.match(r"([A-Z0-9]{2,12})(?:/|$)", asset or "") if asset else None)
    if m2:
        sym = m2.group(1)
    if sym:
        uid = sym
    if DERIV.search(t) and not ("spot" in t and "will list" in t):
        return item(f"an:{ex}:{R.h(title)}", "cripto", "context", name, title=title, es=f"{name}: nuevos derivados ({title[:90]})", en=title,
                    why="Anuncio de productos derivados (futuros, opciones o margen).", why_en="Derivatives product announcement.",
                    act="Los derivados con apalancamiento pueden hacerte perder más de lo que pones: no son para empezar.",
                    act_en="Leveraged derivatives can lose more than you put in; not for beginners.",
                    s=40, opp=1, risk="muy_alto", tags=["derivados"], url=url, pub=iso(rel) if rel else None)
    if "delist" in t or "remove" in t or "cease" in t:
        kind, s, opp, es, act = "alert", 55, 1, f"{name} retirará un activo: {title}", "Si tienes ese activo en ese exchange, revisa plazos para retirarlo o venderlo."
    elif "launchpool" in t or "hodler airdrop" in t or "megadrop" in t or "airdrop" in t:
        kind, s, opp = "launch", 86, 3
        es = f"{name}: {('Launchpool' if 'launchpool' in t else 'airdrop')} de {asset or 'un nuevo token'}"
        act = "Si ya tienes los activos requeridos en el exchange, participar no cuesta más que bloquearlos; revisa fechas y condiciones en el anuncio."
    elif any(w in t for w in ("will list", "to list", "lists", "listing", "will add", "adds", "pre-market", "futures will launch", "will launch")):
        kind, s, opp = "listing", 82 if ex == "binance" else 70, 3 if ex == "binance" else 2
        es = f"{name} listará {asset}" if asset else f"{name} anuncia un nuevo listado: {title}"
        act = "Los anuncios de listado suelen mover el precio antes de que empiece a cotizar. Si ya cotiza en otro sitio, ojo a la volatilidad; no persigas subidas verticales."
    elif any(w in t for w in ("migration", "rebrand", "swap", "upgrade", "network")):
        kind, s, opp, es, act = "context", 44, 1, f"{name}: {title}", "Solo te afecta si tienes ese token en el exchange."
    else:
        kind, s, opp, es, act = "listing", 62, 2, f"{name}: {title}", "Lee el anuncio oficial para ver fechas y pares."
    return item(f"an:{ex}:{uid}", "lanzamientos", kind, name, title=title, es=es, en=title, sym=sym,
                why="Anuncio oficial del exchange.", why_en="Official exchange announcement.", act=act,
                act_en="Read the official announcement for dates and conditions; expect volatility.",
                s=s, opp=opp, risk="alto", tags=["listado" if kind == "listing" else kind], also=["cripto"], url=url,
                pub=iso(rel) if rel else None)


# ------------------------------------------------------------------ DeFi
def c_defillama(ctx: Ctx) -> list[dict]:
    data = get_json("https://api.llama.fi/protocols", timeout=40)
    if not isinstance(data, list):
        raise SourceError("respuesta inesperada")
    out = []
    now = ctx.now.timestamp()
    for p in data:
        tvl, ch1, ch7 = p.get("tvl") or 0, p.get("change_1d"), p.get("change_7d")
        cat = p.get("category") or ""
        if cat in ("CEX", "Chain", "Bridge") or not p.get("slug"):
            continue
        slug, name, sym = p["slug"], p.get("name") or p["slug"], p.get("symbol") or "-"
        url = f"https://defillama.com/protocol/{slug}"
        m = {"tvl": tvl, "ch1d": _r(ch1), "ch7d": _r(ch7), "cat": cat, "chains": (p.get("chains") or [])[:4], "cur": "USD"}
        listed = p.get("listedAt")
        if listed and now - listed < 21 * 86400 and tvl >= 5e6 and (ch7 is None or ch7 >= 15):
            no_token = sym in ("-", "", None)
            s = R.log_score(tvl, 5e6, 5e8, 58, 78) + (8 if no_token else 0)
            days = int((now - listed) / 86400)
            out.append(item(f"dn:{slug}", "lanzamientos", "launch", "DefiLlama",
                            title=f"Nuevo protocolo DeFi con tracción: {name} ({R.fmt_usd(tvl)} en {days} días)",
                            es=f"Nuevo protocolo DeFi con tracción: {name} ({R.fmt_usd(tvl)} depositados en {days} días)",
                            en=f"New DeFi protocol gaining traction: {name} ({R.fmt_usd(tvl, 'en')} TVL in {days} days)",
                            why=(f"Categoría {cat}. " + ("Todavía no tiene token propio: muchos protocolos así acaban recompensando a sus primeros usuarios con un airdrop."
                                                         if no_token else f"Ya tiene token ({sym}).")),
                            why_en=f"Category {cat}. " + ("No token yet: many such protocols later reward early users with an airdrop." if no_token else f"Token: {sym}."),
                            act="Si lo pruebas, usa poco dinero y una wallet aparte; comprueba auditorías en DefiLlama. Nadie garantiza un airdrop y los contratos nuevos pueden tener fallos.",
                            act_en="If you try it, use little money and a separate wallet; check audits. No airdrop is guaranteed and new contracts can fail.",
                            m=m, s=s, opp=3 if no_token else 2, risk="muy_alto", tags=["defi"] + (["sin_token"] if no_token else []),
                            also=["cripto"], url=url))
            continue
        if tvl >= 3e7 and ch1 is not None and 15 <= ch1 <= 400:
            s = 55 + min(20, (ch1 - 15) * 0.6) + (5 if tvl >= 2e8 else 0)
            out.append(item(f"df:{slug}:{ctx.today}", "cripto", "defi", "DefiLlama",
                            title=f"{name}: depósitos (TVL) {R.fmt_pct(ch1)} en 24 h hasta {R.fmt_usd(tvl)}",
                            es=f"{name}: los depósitos (TVL) suben un {R.fmt_pct(ch1)[1:]} en 24 h hasta {R.fmt_usd(tvl)}",
                            en=f"{name}: TVL {ch1:+.1f}% in 24h to {R.fmt_usd(tvl, 'en')}",
                            why=f"Entra dinero rápido en un protocolo de {cat}" + (f" y su token es {sym}." if sym not in ("-", "") else " (sin token propio)."),
                            why_en=f"Money is flowing fast into a {cat} protocol.",
                            act="Comprueba por qué (incentivos, nueva cadena, campaña de puntos). Si hay token, compara la subida del TVL con la de su precio.",
                            act_en="Check why (incentives, new chain, points campaign). If there's a token, compare TVL growth with price.",
                            sym=sym if sym not in ("-", "") else None, m=m, s=int(s), opp=2, risk="alto", tags=["defi"], url=url))
    return out


# ------------------------------------------------------------------ bolsa (Finnhub, Massive)
def _fh(path: str, params: dict) -> dict | list:
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        raise SourceError("falta FINNHUB_API_KEY")
    return get_json(FH + path, params={**params, "token": key}, timeout=20)


def us_session(now: datetime) -> str:
    """'open' en horario regular, 'ext' en pre/post, 'closed' el resto (sin festivos)."""
    t = now.astimezone(NY)
    if t.weekday() >= 5:
        return "closed"
    mins = t.hour * 60 + t.minute
    if 570 <= mins < 960:
        return "open"
    if 240 <= mins < 570 or 960 <= mins < 1200:
        return "ext"
    return "closed"


def _mcap_musd(ctx: Ctx, sym: str) -> float | None:
    f = ctx.fund.get(sym) or {}
    return ((f.get("m") or {}).get("mcap")) if isinstance(f, dict) else None


def c_fh_quotes(ctx: Ctx) -> list[dict]:
    sess = us_session(ctx.now)
    mem = ctx.mem("quotes")
    ticker = ctx.mem("ticker_us")
    out = []
    if sess == "closed" and ticker.get("at") and (ctx.now - parse_date(ticker["at"])).total_seconds() < 6 * 3600:
        return out
    for sym in ("SPY", "QQQ"):
        q = _fh("/quote", {"symbol": sym}) or {}
        if q.get("c"):
            ticker[sym] = {"p": q["c"], "ch": _r(q.get("dp"))}
    ticker["at"] = iso(ctx.now)
    if sess != "open":
        return out
    watch = [s for s in ctx.watch if s not in ("SPY", "QQQ")]
    if not watch:
        return out
    ptr = mem.get("ptr", 0) % len(watch)
    batch = (watch[ptr:] + watch[:ptr])[:16]
    mem["ptr"] = (ptr + 16) % len(watch)
    day = ctx.now.astimezone(NY).date().isoformat()
    for sym in batch:
        try:
            q = _fh("/quote", {"symbol": sym}) or {}
        except SourceError:
            break
        dp, c = q.get("dp"), q.get("c")
        if not c or dp is None:
            continue
        mcap = _mcap_musd(ctx, sym)
        thr = 5 if (mcap or 0) >= 10_000 else 7 if (mcap or 0) >= 2_000 else 10
        if abs(dp) < thr:
            continue
        up = dp > 0
        b = R.move_bucket(dp, (thr, thr * 2, thr * 4, thr * 7))
        name = ((ctx.fund.get(sym) or {}).get("name") or sym)[:40]
        s = R.score_move(dp * (10 / thr), None, (mcap or 0) * 1e6 or None, 10)
        out.append(item(f"sm:{sym}:{day}:{'u' if up else 'd'}{b}", "bolsa", "move", "Finnhub",
                        title=f"{sym} ({name}) {'sube' if up else 'cae'} un {R.fmt_pct(abs(dp))[1:]} hoy",
                        es=f"{sym} ({name}) {'sube' if up else 'cae'} un {R.fmt_pct(abs(dp))[1:]} hoy",
                        en=f"{sym} ({name}) {'up' if up else 'down'} {abs(dp):.1f}% today",
                        why=(f"Movimiento intradía fuerte para una empresa de {R.fmt_usd(mcap * 1e6)} de capitalización." if mcap
                             else "Movimiento intradía fuerte.") + " Suele haber una noticia detrás (resultados, fusión, guía, analistas).",
                        why_en="Strong intraday move; usually driven by news (earnings, M&A, guidance, analysts).",
                        act=("Busca la causa en Noticias. Si entras, define stop y no persigas huecos grandes." if up
                             else "Puede ser una sobrerreacción, pero espera a que se estabilice y revisa la noticia antes de comprar."),
                        act_en=("Find the cause in News. If you buy, set a stop; don't chase big gaps." if up
                                else "Could be an overreaction, but wait for stabilisation and read the news first."),
                        sym=sym, m={"price": c, "cur": "USD", "ch24h": _r(dp), "mcap": mcap * 1e6 if mcap else None},
                        s=s, opp=2, risk="alto", tags=["subida" if up else "caida"], url=f"https://finance.yahoo.com/quote/{sym}"))
    return out


def c_fh_news(ctx: Ctx) -> list[dict]:
    out = []
    for cat, default in (("general", "bolsa"), ("merger", "bolsa"), ("crypto", "cripto")):
        rows = _fh("/news", {"category": cat}) or []
        for n in rows[:40]:
            pub = parse_date(n.get("datetime"))
            if pub and ctx.now - pub > timedelta(hours=30):
                continue
            src = (n.get("source") or "Finnhub").strip()
            out.append(news_item(src, n.get("headline"), n.get("url"), n.get("summary"), pub, default, ctx,
                                 extra_tags=["fusion"] if cat == "merger" else [], via="Finnhub"))
    return [x for x in out if x]


def c_fh_calendar(ctx: Ctx) -> list[dict]:
    out = []
    today = ctx.now.astimezone(NY).date()
    ipo = (_fh("/calendar/ipo", {"from": today.isoformat(), "to": (today + timedelta(days=14)).isoformat()}) or {}).get("ipoCalendar") or []
    for x in ipo:
        if x.get("status") not in ("expected", "priced"):
            continue
        name, sym, date = x.get("name") or "?", x.get("symbol") or "", x.get("date") or ""
        val = x.get("totalSharesValue") or 0
        try:
            days = (datetime.fromisoformat(date).date() - today).days
        except ValueError:
            days = 99
        s = 58 + (10 if val >= 5e8 else 5 if val >= 1e8 else 0) + (8 if 0 <= days <= 3 else 0)
        price = x.get("price") or "?"
        out.append(item(f"ipo:{sym or R.h(name)}:{date}", "lanzamientos", "ipo", "Finnhub",
                        title=f"Salida a bolsa: {name}{f' ({sym})' if sym else ''} el {date} en {x.get('exchange') or 'EE. UU.'}",
                        es=f"Salida a bolsa: {name}{f' ({sym})' if sym else ''} el {date} en {x.get('exchange') or 'EE. UU.'} (precio {price} $)",
                        en=f"IPO: {name}{f' ({sym})' if sym else ''} on {date} on {x.get('exchange') or 'US'} (price {price} $)",
                        why=f"Tamaño de la operación: {R.fmt_usd(val) if val else 'sin dato'}. Las salidas a bolsa grandes atraen atención y volatilidad los primeros días.",
                        why_en=f"Deal size: {R.fmt_usd(val, 'en') if val else 'n/a'}. Big IPOs draw attention and volatility in the first days.",
                        act="Desde España casi nunca se compra al precio de salida; normalmente podrás operar desde el primer día de cotización en tu bróker. Si no tienes experiencia, deja pasar la volatilidad inicial.",
                        act_en="Retail investors rarely get the IPO price; you can usually trade from the first day. Let early volatility pass if inexperienced.",
                        sym=sym or None, m={"date": date, "price": price, "value": val, "shares": x.get("numberOfShares")},
                        s=s, opp=2, risk="alto", tags=["ipo"], also=["bolsa"], url="https://www.nasdaq.com/market-activity/ipos"))
    earn = (_fh("/calendar/earnings", {"from": (today - timedelta(days=1)).isoformat(), "to": (today + timedelta(days=1)).isoformat()}) or {}).get("earningsCalendar") or []
    big = []
    for x in earn:
        sym = x.get("symbol") or ""
        mcap = _mcap_musd(ctx, sym)
        if not mcap or mcap < 5_000:
            continue
        a, e = x.get("epsActual"), x.get("epsEstimate")
        if a is not None and e not in (None, 0):
            surprise = (a - e) / abs(e) * 100
            if abs(surprise) >= 5:
                beat = surprise > 0
                name = ((ctx.fund.get(sym) or {}).get("name") or sym)[:40]
                s = 56 + min(20, abs(surprise) * 0.7) + (6 if mcap >= 50_000 else 0)
                out.append(item(f"eb:{sym}:{x.get('date')}", "bolsa", "earnings", "Finnhub",
                                title=f"{sym} ({name}) {'supera' if beat else 'no alcanza'} previsiones: BPA {a} frente a {e} esperado",
                                es=f"{sym} ({name}) {'supera' if beat else 'no alcanza'} las previsiones: beneficio por acción {a} frente a {e} esperado ({R.fmt_pct(surprise)})",
                                en=f"{sym} ({name}) {'beats' if beat else 'misses'} estimates: EPS {a} vs {e} ({surprise:+.0f}%)",
                                why="Los resultados por encima o por debajo de lo esperado mueven la acción en el pre/post-mercado y los días siguientes.",
                                why_en="Earnings surprises move the stock in extended hours and the following days.",
                                act="Mira la reacción del precio y la guía para el próximo trimestre antes de actuar; un buen dato con mala guía puede hacer caer la acción.",
                                act_en="Check price reaction and next-quarter guidance first; a beat with weak guidance can still fall.",
                                sym=sym, m={"epsActual": a, "epsEstimate": e, "surprise": _r(surprise, 1), "mcap": mcap * 1e6,
                                            "revActual": x.get("revenueActual"), "revEstimate": x.get("revenueEstimate")},
                                s=int(s), opp=2, risk="alto", tags=["resultados"], url=f"https://finance.yahoo.com/quote/{sym}"))
        elif x.get("date") == today.isoformat():
            big.append((mcap, sym, x.get("hour") or ""))
    if big:
        big.sort(reverse=True)
        when = {"bmo": "antes de la apertura", "amc": "tras el cierre"}
        names = ", ".join(f"{s}{f' ({when[h]})' if h in when else ''}" for _, s, h in big[:8])
        out.append(item(f"erd:{today.isoformat()}", "bolsa", "earnings", "Finnhub",
                        title=f"Hoy presentan resultados: {names}", es=f"Hoy presentan resultados: {names}",
                        en="Reporting today: " + ", ".join(s for _, s, _ in big[:8]),
                        why="Los días de resultados son los de más movimiento para cada acción.", why_en="Earnings days are the most volatile for each stock.",
                        act="Si tienes alguna de estas acciones, decide antes qué harás si sube o baja con fuerza.",
                        act_en="If you hold any of these, decide in advance what you'll do on a big move.",
                        s=48, opp=1, risk="medio", tags=["resultados"], url="https://finance.yahoo.com/calendar/earnings"))
    return out


def c_fh_insider(ctx: Ctx) -> list[dict]:
    mem = ctx.mem("insider")
    core = [s for s in ctx.watch if (_mcap_musd(ctx, s) or 0) >= 1_000][:80]
    if not core:
        return []
    ptr = mem.get("ptr", 0) % len(core)
    batch = (core[ptr:] + core[:ptr])[:5]
    mem["ptr"] = (ptr + 5) % len(core)
    out = []
    since = (ctx.now - timedelta(days=30)).date().isoformat()
    week = ctx.now.strftime("%G-W%V")
    for sym in batch:
        d = _fh("/stock/insider-transactions", {"symbol": sym, "from": since}) or {}
        buys = [x for x in d.get("data") or [] if x.get("transactionCode") == "P" and (x.get("change") or 0) > 0
                and (x.get("transactionDate") or "") >= since]
        total = sum((x.get("change") or 0) * (x.get("transactionPrice") or 0) for x in buys)
        people = {x.get("name") for x in buys}
        if total >= 250_000 and (len(people) >= 2 or total >= 1_000_000):
            s = R.log_score(total, 2.5e5, 2e7, 60, 84) + (4 if len(people) >= 3 else 0)
            out.append(item(f"in:{sym}:{week}", "bolsa", "insider", "Finnhub",
                            title=f"Directivos de {sym} compran acciones: {len(people)} personas, {R.fmt_usd(total)} en 30 días",
                            es=f"Directivos de {sym} compran acciones con su dinero: {len(people)} personas, {R.fmt_usd(total)} en 30 días",
                            en=f"{sym} insiders buying: {len(people)} people, {R.fmt_usd(total, 'en')} in 30 days",
                            why="Los directivos venden por muchos motivos, pero solo compran por uno: creen que la acción subirá. Las compras en grupo son una señal clásica de «dinero listo».",
                            why_en="Insiders sell for many reasons but buy for one: they expect the stock to rise. Cluster buys are a classic smart-money signal.",
                            act="Úsalo como filtro, no como orden de compra: revisa valoración y noticias en la pestaña Bolsa.",
                            act_en="Use it as a filter, not a buy order: check valuation and news.",
                            sym=sym, m={"total": total, "insiders": len(people), "buys": len(buys)}, s=s, opp=3 if total >= 1e6 else 2,
                            risk="medio", tags=["insider"], url=f"https://finance.yahoo.com/quote/{sym}/insider-transactions"))
    return out


def c_massive_eod(ctx: Ctx) -> list[dict]:
    key = os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY")
    if not key:
        raise SourceError("falta MASSIVE_API_KEY")
    mem = ctx.mem("eod")
    t = ctx.now.astimezone(NY)
    last = t.date() if (t.hour >= 17 and t.weekday() < 5) else t.date() - timedelta(days=1)
    while last.weekday() >= 5:
        last -= timedelta(days=1)
    if mem.get("done") == last.isoformat():
        return []
    rows, days, d = {}, [], last
    for _ in range(6):
        if len(days) == 2:
            break
        if d.weekday() < 5:
            try:
                r = get_json(f"https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/{d.isoformat()}",
                             params={"adjusted": "true", "apiKey": key}, timeout=40) or {}
            except SourceError as e:
                if "403" not in str(e):
                    raise
                r = {}  # el plan gratuito no da el día en curso: probar el anterior
            res = r.get("results") or []
            if res:
                days.append(d.isoformat())
                rows[d.isoformat()] = {x["T"]: x for x in res}
        d -= timedelta(days=1)
    if len(days) < 2:
        raise SourceError("sin datos de cierre")
    cur, prev = rows[days[0]], rows[days[1]]
    moves = []
    for sym, x in cur.items():
        p = prev.get(sym)
        if not p or not p.get("c") or x.get("c", 0) < 5 or "." in sym or len(sym) > 5:
            continue
        dv = x["c"] * x.get("v", 0)
        if dv < 3e7:
            continue
        pct = (x["c"] / p["c"] - 1) * 100
        moves.append((pct, sym, x["c"], dv))
    moves.sort()
    picks = [m for m in moves[::-1][:8] if m[0] >= 8] + [m for m in moves[:5] if m[0] <= -12]
    out = []
    for pct, sym, c, dv in picks:
        up = pct > 0
        name = ((ctx.fund.get(sym) or {}).get("name") or sym)[:40]
        out.append(item(f"eod:{sym}:{days[0]}", "bolsa", "move", "Massive",
                        title=f"{sym} ({name}) cerró el {days[0]} con un {R.fmt_pct(pct)} y {R.fmt_usd(dv)} negociados",
                        es=f"{sym} ({name}) cerró el {days[0]} con un {R.fmt_pct(pct)} y {R.fmt_usd(dv)} negociados",
                        en=f"{sym} closed {days[0]} {pct:+.1f}% on {R.fmt_usd(dv, 'en')} volume",
                        why="Entre los mayores movimientos del día en EE. UU. con mucho volumen.", why_en="Among the day's biggest US movers on heavy volume.",
                        act="Busca la causa antes de la próxima sesión; los gaps fuertes suelen continuar o revertir en los días siguientes.",
                        act_en="Find the cause before the next session; big gaps often continue or reverse in the following days.",
                        sym=sym, m={"price": c, "cur": "USD", "ch24h": _r(pct), "dollarVol": dv}, s=int(50 + min(25, (abs(pct) - 8) * 1.2)),
                        opp=2, risk="alto", tags=["subida" if up else "caida", "cierre"], url=f"https://finance.yahoo.com/quote/{sym}"))
    mem["done"] = days[0]
    return out


# ------------------------------------------------------------------ redes sociales
def c_stocktwits(ctx: Ctx) -> list[dict]:
    d = get_json("https://api.stocktwits.com/api/2/trending/symbols.json") or {}
    out, syms = [], []
    for i, x in enumerate((d.get("symbols") or [])[:20]):
        sym = (x.get("symbol") or "").upper()
        if not sym:
            continue
        crypto = sym.endswith(".X")
        base = sym[:-2] if crypto else sym
        syms.append(base)
        title = x.get("title") or base
        out.append(item(f"st:{sym}:{ctx.today}", "cripto" if crypto else "bolsa", "social", "StockTwits",
                        title=f"{base} ({title}) en tendencia en StockTwits (#{i + 1})", es=f"{base} ({title}) en tendencia en StockTwits (#{i + 1})",
                        en=f"{base} ({title}) trending on StockTwits (#{i + 1})",
                        why="Está entre los valores más comentados por inversores particulares ahora mismo: más atención suele traer más volatilidad.",
                        why_en="Among the most discussed tickers by retail investors right now; attention brings volatility.",
                        act="Comprueba si hay noticia y cómo se mueve el precio; la euforia de redes dura poco.",
                        act_en="Check for news and price action; social hype fades fast.",
                        sym=base, s=int(42 + max(0, 20 - i) * 0.8), opp=2 if i < 5 else 1, risk="alto", tags=["redes"],
                        url=f"https://stocktwits.com/symbol/{sym}"))
    ctx.setmem("st_syms", syms[:20])
    return out


APE_SKIP = {"SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "TQQQ", "SQQQ", "SPX", "NDX", "VIX", "UVXY", "CIA", "HR", "AM", "ET", "NYT", "AI",
            "DD", "CEO", "USA", "EU", "UK", "IT", "ON", "ALL", "ARE", "FOR", "NOW", "YOLO", "OPEN", "LOVE", "BIG", "CAN", "HAS", "GO", "SO",
            "ONE", "REAL", "BE", "RH", "EV", "PM", "AT", "CASH", "FUN", "GOOD", "VERY", "RUN", "EAT", "LOW", "HIGH", "NEW", "FREE", "TV",
            "TA", "IMO", "ATH", "FOMO", "ELON", "PUMP", "MOON", "WSB", "OR", "IRS", "FBI", "GDP", "CPI", "FED", "SEC", "BTC", "ETH",
            "USDT", "USDC", "OUT", "BUY", "SELL", "HOLD", "LIFE", "PLAY", "NICE", "WELL", "TOP", "BEST", "JUST", "LINK", "MAIN", "SAFE"}


def c_apewisdom(ctx: Ctx) -> list[dict]:
    out, top = [], []
    for kind, cat in (("all-stocks", "bolsa"), ("all-crypto", "cripto")):
        d = get_json(f"https://apewisdom.io/api/v1.0/filter/{kind}/page/1") or {}
        for x in d.get("results") or []:
            t = (x.get("ticker") or "").upper()
            men, men0 = x.get("mentions") or 0, x.get("mentions_24h_ago") or 0
            rank, rank0 = x.get("rank") or 999, x.get("rank_24h_ago") or 999
            if cat == "bolsa" and rank <= 25:
                top.append(t)
            if t in APE_SKIP or (cat == "bolsa" and men < 60):
                continue
            ratio = men / max(1, men0)
            jump = (rank0 - rank) if rank0 and rank0 < 900 else 0
            if men < 40 or not ((ratio >= 3 and men >= 60) or (rank <= 15 and jump >= 20)):
                continue
            name = R.clean(x.get("name") or t)[:40]
            s = 48 + min(22, ratio * 3) + (6 if rank <= 10 else 0)
            out.append(item(f"ape:{cat}:{t}:{ctx.today}", cat, "social", "Reddit",
                            title=f"{t} ({name}) dispara sus menciones en Reddit: {men} en 24 h (×{ratio:.1f})",
                            es=f"{t} ({name}) dispara sus menciones en Reddit: {men} en 24 h (×{ratio:.1f}), puesto #{rank}",
                            en=f"{t} ({name}) Reddit mentions surge: {men} in 24h (×{ratio:.1f}), rank #{rank}",
                            why="Explosión de conversación en foros como wallstreetbets o CryptoCurrency (datos de ApeWisdom): atención minorista que puede mover el precio a corto plazo.",
                            why_en="Conversation spike on forums like wallstreetbets or CryptoCurrency (ApeWisdom data): retail attention can move price short term.",
                            act="Mira el precio y la noticia antes de subirte: cuando todo el mundo habla de algo, a menudo ya es tarde.",
                            act_en="Check price and news first: when everyone is talking about it, it's often late.",
                            sym=t, m={"mentions": men, "mentions24hAgo": men0, "rank": rank, "rank24hAgo": rank0},
                            s=int(s), opp=2 if ratio >= 4 else 1, risk="alto", tags=["redes"],
                            url=f"https://apewisdom.io/{'stocks' if cat == 'bolsa' else 'cryptocurrencies'}/{t}/"))
    ctx.setmem("ape_top", top)
    return out


FIN_TECH = R._kw("stock", "market", "crypto", "bitcoin", "ethereum", "ai ", "openai", "nvidia", "tesla", "apple", "startup", "ipo", "fed",
                 "earnings", "economy", "inflation", "tariff", "bank", "musk", "google", "microsoft", "meta", "amazon", "chip", "invest",
                 "funding", "billion", "shares", "token", "airdrop", "nasdaq", "dow", "s&p")


def c_bluesky(ctx: Ctx) -> list[dict]:
    d = get_json("https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics") or {}
    out = []
    for x in (d.get("topics") or [])[:25]:
        name, desc = x.get("displayName") or x.get("topic") or "", x.get("description") or ""
        text = f" {R.fold(name)} {R.fold(desc)} "
        if not any(w in text for w in FIN_TECH):
            continue
        cls = R.classify(name, desc, "bolsa")
        out.append(item(f"bs:{R.h(name)}:{ctx.today}", cls["cat"], "social", "Bluesky", title=f"Tendencia en Bluesky: {name}",
                        es=f"Tendencia en Bluesky: {name}", en=f"Trending on Bluesky: {name}", sum=desc,
                        why="Tema del que más se habla ahora en Bluesky.", why_en="One of the most discussed topics on Bluesky now.",
                        act="Útil para enterarte rápido; confirma en Noticias antes de actuar.", act_en="Good early signal; confirm in News before acting.",
                        s=44 + min(10, int(cls["intent"] / 2)), opp=1, risk="medio", tags=["redes"] + cls["tags"][:2],
                        also=cls["also"], url=f"https://bsky.app{x.get('link') or ''}"))
    mem = ctx.mem("bsky")
    queries = ["airdrop", "IPO", "earnings beat", "startup funding", "launchpool", "insider buying"]
    i = mem.get("q", 0)
    for q in (queries[i % len(queries)], queries[(i + 1) % len(queries)]):
        r = get_json("https://api.bsky.app/xrpc/app.bsky.feed.searchPosts", params={"q": q, "sort": "top", "limit": 25,
                                                                                   "since": iso(ctx.now - timedelta(hours=12))}) or {}
        for p in r.get("posts") or []:
            likes = p.get("likeCount") or 0
            rec = p.get("record") or {}
            text = R.clean(rec.get("text") or "")
            if likes < 40 or len(text) < 40:
                continue
            handle = (p.get("author") or {}).get("handle") or ""
            pid = (p.get("uri") or "").rsplit("/", 1)[-1]
            cls = R.classify(text[:200], "", "bolsa")
            if cls["noise"]:
                continue
            out.append(item(f"bp:{pid}", cls["cat"], "social", "Bluesky", title=text[:200], sum=f"@{handle} · {likes} me gusta",
                            why="Publicación con mucha interacción en Bluesky.", why_en="Highly engaged Bluesky post.",
                            act="Confirma con una fuente fiable antes de actuar.", act_en="Confirm with a reliable source before acting.",
                            s=40 + min(14, likes // 40), opp=1, risk="alto", tags=["redes"] + cls["tags"][:2], also=cls["also"],
                            url=f"https://bsky.app/profile/{handle}/post/{pid}"))
    mem["q"] = i + 2
    return out


def c_mastodon(ctx: Ctx) -> list[dict]:
    d = get_json("https://mastodon.social/api/v1/trends/links", params={"limit": 20}) or []
    out = []
    for x in d:
        title, desc = x.get("title") or "", x.get("description") or ""
        text = f" {R.fold(title)} {R.fold(desc)} "
        if not any(w in text for w in FIN_TECH):
            continue
        it = news_item(f"Mastodon · {x.get('provider_name') or 'enlace'}", title, x.get("url"), desc, None, "bolsa", ctx, kind="social")
        if it:
            it["s"] = max(30, it["s"] - 6)
            out.append(it)
    return out


def c_hn(ctx: Ctx) -> list[dict]:
    out = []
    d = get_json("https://hn.algolia.com/api/v1/search", params={"tags": "front_page", "hitsPerPage": 30}) or {}
    since = int(ctx.now.timestamp()) - 2 * 86400
    s2 = get_json("https://hn.algolia.com/api/v1/search_by_date", params={"tags": "show_hn", "numericFilters": f"points>60,created_at_i>{since}",
                                                                          "hitsPerPage": 20}) or {}
    for hset, show in ((d.get("hits") or [], False), (s2.get("hits") or [], True)):
        for x in hset:
            pts = x.get("points") or 0
            if (not show and pts < 200) or not x.get("title"):
                continue
            title = re.sub(r"^(Show|Launch) HN:\s*", "", x["title"])
            hn = f"https://news.ycombinator.com/item?id={x.get('objectID')}"
            cls = R.classify(title, "", "ia")
            cat = cls["cat"] if cls["cat"] in ("ia", "startups", "cripto", "bolsa", "lanzamientos") else "ia"
            out.append(item(f"hn:{x.get('objectID')}", cat, "launch" if show else "social", "Hacker News", title=title,
                            es=f"{'Lanzamiento en' if show else 'En portada de'} Hacker News: {title}",
                            en=f"{'Launched on' if show else 'Front page of'} Hacker News: {title}",
                            why=f"{pts} puntos y {x.get('num_comments') or 0} comentarios entre desarrolladores y fundadores.",
                            why_en=f"{pts} points and {x.get('num_comments') or 0} comments from developers and founders.",
                            act=("Herramienta nueva con buena acogida: pruébala o úsala como idea de producto." if show
                                 else "Termómetro de lo que interesa en tecnología; útil para detectar tendencias pronto."),
                            act_en="New tool with good reception: try it or use it as a product idea." if show else "Tech pulse; useful to spot trends early.",
                            m={"points": pts, "comments": x.get("num_comments"), "hn": hn},
                            s=R.log_score(pts, 60, 1500, 40, 60) if show else R.log_score(pts, 150, 2000, 34, 54),
                            opp=2 if show or cls["opp"] >= 3 else 1, risk="bajo", tags=["redes"] + cls["tags"][:2],
                            also=[c for c in (cls["also"] + (["lanzamientos"] if show else [])) if c != cat], url=x.get("url") or hn))
    return out


def c_github(ctx: Ctx) -> list[dict]:
    since = (ctx.now - timedelta(days=7)).date().isoformat()
    hdr = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        hdr["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    d = get_json(f"https://api.github.com/search/repositories?q=created:%3E{since}+stars:%3E300&sort=stars&order=desc&per_page=12", headers=hdr) or {}
    out = []
    for r in d.get("items") or []:
        stars = r.get("stargazers_count") or 0
        days = max(1, (ctx.now - parse_date(r.get("created_at"))).days) if r.get("created_at") else 7
        out.append(item(f"gh:{r['full_name']}", "ia", "trend", "GitHub", title=f"{r['full_name']}: {(r.get('description') or '')[:120]}",
                        es=f"Repositorio en tendencia: {r['full_name']} ({stars:,} ★ en {days} días)".replace(",", "."),
                        en=f"Trending repo: {r['full_name']} ({stars:,} stars in {days} days)", sum=r.get("description"),
                        why="Herramienta nueva que despega entre desarrolladores: puede ahorrarte trabajo o anticipar una tendencia.",
                        why_en="A new tool taking off among developers: may save you work or hint at a trend.",
                        act="Pruébala si encaja con lo que haces. No es una inversión.", act_en="Try it if it fits your work. Not an investment.",
                        m={"stars": stars, "lang": r.get("language")}, s=R.log_score(stars, 300, 10000, 36, 58), opp=1, risk="bajo",
                        tags=["codigo"], url=r.get("html_url")))
    return out


def c_hf(ctx: Ctx) -> list[dict]:
    d = get_json("https://huggingface.co/api/models", params={"sort": "trendingScore", "limit": 10}) or []
    week = ctx.now.strftime("%G-W%V")
    out = []
    for x in d:
        mid = x.get("id") or ""
        if (x.get("trendingScore") or 0) < 80:
            continue
        out.append(item(f"hf:{mid}:{week}", "ia", "trend", "Hugging Face", title=f"Modelo de IA en tendencia: {mid}",
                        es=f"Modelo de IA en tendencia: {mid} ({x.get('likes') or 0} me gusta)", en=f"Trending AI model: {mid}",
                        why="Modelos abiertos que despegan: puedes usarlos gratis para crear productos o automatizar tareas.",
                        why_en="Open models taking off: free to build products or automate tasks with.",
                        act="Si construyes con IA, pruébalo en Hugging Face.", act_en="If you build with AI, try it on Hugging Face.",
                        m={"likes": x.get("likes"), "downloads": x.get("downloads"), "trending": x.get("trendingScore")},
                        s=R.log_score(x.get("trendingScore") or 80, 80, 2000, 38, 56), opp=1, risk="bajo", tags=["modelo"],
                        url=f"https://huggingface.co/{mid}"))
    return out


# ------------------------------------------------------------------ noticias
def news_item(src: str, title: str | None, url: str | None, summary: str | None, pub: datetime | None, default_cat: str, ctx: Ctx,
              *, extra_tags=(), via: str | None = None, kind: str = "news") -> dict | None:
    title = R.clean(title)
    if len(title) < 12:
        return None
    summary = R.clean(summary)
    if summary.lower().startswith(title.lower()[:40]):
        summary = summary[len(title):].strip(" -–:")
    cls = R.classify(title, summary, default_cat)
    if cls["noise"]:
        return None
    age = (ctx.now - pub).total_seconds() / 3600 if pub else None
    if age is not None and age > 48:
        return None
    s = R.score_news(src, cls, age)
    cu = R.canon_url(url)
    nid = "n:" + (R.h(cu) if cu and "news.google.com" not in cu else R.h(R.fold(title)[:90]))
    risk = "alto" if cls["cat"] in ("cripto", "lanzamientos") else "medio"
    return item(nid, cls["cat"], kind, src, title=title, url=url or "", sum=summary, s=s, opp=cls["opp"], risk=risk,
                tags=list(cls["tags"]) + list(extra_tags), also=cls["also"], pub=iso(pub) if pub else None,
                srcs=[{"n": src, "u": url}] if url else None) | ({"via": via} if via else {})


def decode(r) -> str:
    """Texto de un feed respetando la codificación declarada en el XML (muchos no la ponen en la cabecera HTTP)."""
    raw = r.content if hasattr(r, "content") and isinstance(r.content, (bytes, bytearray)) else None
    if raw is None:
        return r.text
    m = re.match(rb"^\s*(?:\xef\xbb\xbf)?<\?xml[^>]*encoding=[\"']([A-Za-z0-9_\-]+)", raw)
    enc = m.group(1).decode() if m else "utf-8"
    try:
        return raw.decode(enc, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def parse_feed(xml_text: str) -> list[dict]:
    xml_text = re.sub(r"^\s*<\?xml[^>]*\?>", "", xml_text.lstrip("﻿")).strip()
    root = ET.fromstring(xml_text)
    out = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        kids = {}
        for c in it:
            kids.setdefault(c.tag.split("}")[-1], c)

        def get(*names):
            return next((kids[n] for n in names if n in kids), None)
        title_el = get("title")
        title = (title_el.text if title_el is not None else "") or ""
        link = ""
        links = [c for c in it if c.tag.split("}")[-1] == "link"]
        for le in links:
            if (le.text or "").strip():
                link = le.text.strip()
                break
            if le.get("href") and le.get("rel", "alternate") == "alternate":
                link = le.get("href")
                break
        if not link and links and links[0].get("href"):
            link = links[0].get("href")
        if not link:
            g = get("guid", "id")
            link = (g.text or "") if g is not None and (g.text or "").startswith("http") else ""
        desc_el = get("description", "summary", "encoded", "content")
        desc = desc_el.text if desc_el is not None and desc_el.text else ""
        date_el = get("pubDate", "published", "updated", "date")
        src_el = get("source")
        out.append({"title": title.strip(), "url": link.strip(), "summary": desc[:1500], "date": date_el.text if date_el is not None else None,
                    "source": (src_el.text or "").strip() if src_el is not None else None})
    return out


def rss_collector(feed: dict):
    def run(ctx: Ctx) -> list[dict]:
        r = fetch(feed["url"], etags=ctx.etags, timeout=20)
        if r is None:
            return []
        out = []
        for x in parse_feed(decode(r))[:feed.get("max", 30)]:
            pub = parse_date(x["date"])
            src = feed["name"]
            title = x["title"]
            if feed.get("gnews"):
                pubname = x.get("source") or ""
                if pubname and title.endswith(" - " + pubname):
                    title = title[: -len(" - " + pubname)]
                src = pubname or "Google News"
            it = news_item(src, title, x["url"], x["summary"], pub, feed["cat"], ctx, extra_tags=feed.get("tags", ()),
                           via="Google News" if feed.get("gnews") else None, kind=feed.get("kind", "news"))
            if it:
                if feed.get("bonus"):
                    it["s"] = max(0, min(100, it["s"] + feed["bonus"]))
                out.append(it)
        return out
    run.__name__ = "rss_" + re.sub(r"\W+", "_", feed["name"]).lower()
    return run


GNEWS = {
    "en": [("airdrop OR \"points program\" crypto", "lanzamientos"), ("\"will list\" Binance OR Coinbase OR Kraken", "lanzamientos"),
           ("launchpool OR \"token generation event\"", "lanzamientos"), ("IPO filing OR \"prices IPO\"", "lanzamientos"),
           ("\"raises\" seed OR \"Series A\" AI startup", "startups"), ("\"accelerator\" \"applications open\" startups", "startups"),
           ("\"insider buying\" OR \"insider purchase\" stock", "bolsa"), ("\"beats estimates\" shares jump", "bolsa"),
           ("\"free credits\" OR \"startup program\" AI", "ia"), ("hackathon prize AI OR crypto", "ia")],
    "es": [("\"ronda de financiación\" startup", "startups"), ("convocatoria ayudas emprendedores", "startups"),
           ("subvención digitalización pymes", "negocio"), ("aceleradora convocatoria abierta startups", "startups"),
           ("crowdfunding España campaña", "startups"), ("\"salida a bolsa\" OR OPV", "bolsa"),
           ("airdrop criptomonedas", "lanzamientos"), ("inteligencia artificial lanza España empresa", "ia")],
}


def c_gnews(ctx: Ctx) -> list[dict]:
    mem = ctx.mem("gnews")
    qs = [("en", q, c) for q, c in GNEWS["en"]] + ([("es", q, c) for q, c in GNEWS["es"]] if ctx.region in ("es", "latam", "global") else [])
    i = mem.get("i", 0)
    pick = [qs[(i + k) % len(qs)] for k in range(3)]
    mem["i"] = (i + 3) % len(qs)
    out = []
    for lang, q, cat in pick:
        params = ("hl=en-US&gl=US&ceid=US:en" if lang == "en" else "hl=es&gl=ES&ceid=ES:es")
        url = f"https://news.google.com/rss/search?q={quote_plus(q + ' when:1d')}&{params}"
        out += rss_collector({"name": "Google News", "url": url, "cat": cat, "gnews": True, "max": 12})(ctx)
    return out


BDNS_Q = ["emprendedores", "startups", "empresas emergentes", "creación de empresas", "digitalización", "innovación",
          "autónomos", "inteligencia artificial", "comercio electrónico", "internacionalización", "jóvenes empresarios", "I+D"]
BDNS_BAD = R._kw("nominativa", "concesion directa", "ibi", "bienes inmuebles", "comedor", "a favor de", "convenio con", "club ",
                 "cofradia", "parroquia", "fiestas", "asociacion de vecinos", "ampa", "transporte escolar", "a la asociacion",
                 "a la fundacion", "al ayuntamiento", "a la federacion", "festival", "cabalgata")
BDNS_GOOD = R._kw("emprend", "empresa", "pyme", "autonom", "startup", "emergente", "digital", "innovacion", "i+d", "comercio",
                  "industria", "internacionaliz", "tecnolog", "inteligencia artificial", "negocio", "creacion de", "contratacion",
                  "economia social", "agroaliment", "turismo", "energia", "eficiencia")


def c_bdns(ctx: Ctx) -> list[dict]:
    if ctx.region != "es":
        return []
    mem = ctx.mem("bdns")
    i = mem.get("i", 0)
    qs = [BDNS_Q[(i + k) % len(BDNS_Q)] for k in range(4)]
    mem["i"] = (i + 4) % len(BDNS_Q)
    out, seen = [], set()
    for q in qs:
        d = get_json("https://www.infosubvenciones.es/bdnstrans/api/convocatorias/busqueda",
                     params={"vpd": "GE", "page": 0, "pageSize": 20, "order": "fechaRecepcion", "direccion": "desc", "descripcion": q},
                     timeout=25) or {}
        for x in d.get("content") or []:
            num, desc = str(x.get("numeroConvocatoria") or ""), R.clean(x.get("descripcion") or "")
            if not num or num in seen:
                continue
            seen.add(num)
            f = R.fold(desc)
            fecha = parse_date(x.get("fechaRecepcion"))
            if (fecha and ctx.now - fecha > timedelta(days=10)) or any(w in f for w in BDNS_BAD) or not any(w in f for w in BDNS_GOOD):
                continue
            nivel = (x.get("nivel1") or "").upper()
            org = R.clean(x.get("nivel2") or x.get("nivel3") or "")
            s = {"ESTADO": 72, "AUTONOMICA": 66, "LOCAL": 56}.get(nivel, 58)
            if any(w in f for w in R._kw("emprend", "startup", "emergente", "creacion de empresas", "nuevas empresas")):
                s += 6
            where = org.title() if org else nivel.title()
            out.append(item(f"gr:{num}", "startups", "grant", "BDNS", title=desc[:200],
                            es=f"Ayuda pública ({where}): {desc[:170]}", en=f"Public grant in Spain ({where}): {desc[:170]}",
                            why=f"Convocatoria oficial registrada en la Base de Datos Nacional de Subvenciones el {x.get('fechaRecepcion')}.",
                            why_en=f"Official call registered in Spain's national grants database on {x.get('fechaRecepcion')}.",
                            act="Abre la ficha oficial, revisa quién puede pedirla y el plazo (suele ser corto) y prepara la documentación.",
                            act_en="Open the official page, check eligibility and deadline (often short) and prepare documents.",
                            m={"nivel": nivel, "org": org, "fecha": x.get("fechaRecepcion")}, s=s, opp=3, risk="bajo",
                            tags=["ayuda"], also=["negocio"], url=f"https://www.infosubvenciones.es/bdnstrans/GE/es/convocatorias/{num}",
                            pub=iso(fecha) if fecha else None))
    return out


# ------------------------------------------------------------------ registro
DEFAULT_FEEDS = [
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "cat": "cripto"},
    {"name": "Cointelegraph", "url": "https://cointelegraph.com/rss", "cat": "cripto"},
    {"name": "Decrypt", "url": "https://decrypt.co/feed", "cat": "cripto"},
    {"name": "The Block", "url": "https://www.theblock.co/rss.xml", "cat": "cripto"},
    {"name": "Blockworks", "url": "https://blockworks.co/feed", "cat": "cripto"},
    {"name": "CryptoSlate", "url": "https://cryptoslate.com/feed/", "cat": "cripto"},
    {"name": "The Defiant", "url": "https://thedefiant.io/api/feed", "cat": "cripto", "every": 15},
    {"name": "Bitcoin Magazine", "url": "https://bitcoinmagazine.com/feed", "cat": "cripto", "every": 15},
    {"name": "DL News", "url": "https://www.dlnews.com/arc/outboundfeeds/rss/", "cat": "cripto", "every": 15},
    {"name": "Kraken blog", "url": "https://blog.kraken.com/feed", "cat": "lanzamientos", "every": 15, "bonus": 6},
    {"name": "CNBC", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "cat": "bolsa"},
    {"name": "CNBC Markets", "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html", "cat": "bolsa"},
    {"name": "MarketWatch", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "cat": "bolsa"},
    {"name": "Seeking Alpha", "url": "https://seekingalpha.com/market_currents.xml", "cat": "bolsa"},
    {"name": "Benzinga", "url": "https://www.benzinga.com/feed", "cat": "bolsa"},
    {"name": "Investing.com", "url": "https://es.investing.com/rss/news.rss", "cat": "bolsa"},
    {"name": "Expansión", "url": "https://e00-expansion.uecdn.es/rss/mercados.xml", "cat": "bolsa", "every": 10},
    {"name": "TechCrunch Startups", "url": "https://techcrunch.com/category/startups/feed/", "cat": "startups"},
    {"name": "TechCrunch Venture", "url": "https://techcrunch.com/category/venture/feed/", "cat": "startups", "every": 15},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "cat": "ia"},
    {"name": "Crunchbase News", "url": "https://news.crunchbase.com/feed/", "cat": "startups", "every": 15},
    {"name": "Sifted", "url": "https://sifted.eu/feed", "cat": "startups", "every": 15},
    {"name": "El Referente", "url": "https://www.elreferente.es/feed/", "cat": "startups", "every": 15, "bonus": 4},
    {"name": "EU-Startups", "url": "https://www.eu-startups.com/feed/", "cat": "startups", "every": 15},
    {"name": "Wamda", "url": "https://www.wamda.com/feed", "cat": "startups", "every": 30},
    {"name": "TechCabal", "url": "https://techcabal.com/feed/", "cat": "startups", "every": 30},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "cat": "ia", "every": 10},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "cat": "ia", "every": 15},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/", "cat": "ia", "every": 30},
    {"name": "Google AI", "url": "https://blog.google/technology/ai/rss/", "cat": "ia", "every": 30, "bonus": 4},
    {"name": "OpenAI", "url": "https://openai.com/news/rss.xml", "cat": "ia", "every": 60, "max": 15, "bonus": 6},
    {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml", "cat": "ia", "every": 60, "max": 15},
    {"name": "Xataka", "url": "https://www.xataka.com/feedburner.xml", "cat": "ia", "every": 15},
    {"name": "Product Hunt", "url": "https://www.producthunt.com/feed", "cat": "ia", "every": 30, "kind": "launch", "tags": ["producto"], "max": 15},
]


def registry(cfg: dict) -> list[tuple[str, object, int]]:
    """(nombre, función, cada cuántos minutos)."""
    p = cfg.get("pulse") or {}
    feeds = p.get("rss") or DEFAULT_FEEDS
    regs = [("CoinGecko mercado", c_cg_markets, 5), ("CoinGecko tendencias", c_cg_trending, 10), ("Miedo y codicia", c_fng, 60),
            ("Anuncios Binance", c_binance_ann, 10), ("Anuncios OKX", c_okx_ann, 10),
            ("DefiLlama", c_defillama, 30), ("Bolsa EE. UU. (cotizaciones)", c_fh_quotes, 5), ("Noticias Finnhub", c_fh_news, 10),
            ("Calendario IPO y resultados", c_fh_calendar, 60), ("Compras de directivos", c_fh_insider, 30),
            ("Cierre EE. UU. (Massive)", c_massive_eod, 60), ("StockTwits", c_stocktwits, 10), ("Reddit (ApeWisdom)", c_apewisdom, 20),
            ("Bluesky", c_bluesky, 15), ("Mastodon", c_mastodon, 30), ("Hacker News", c_hn, 10), ("GitHub", c_github, 60),
            ("Hugging Face modelos", c_hf, 60), ("Google News", c_gnews, 15), ("Ayudas públicas (BDNS)", c_bdns, 60)]
    regs += [(f"Altas {EX_NAME[ex]}", listing_collector(ex), 15) for ex in EX_NAME]
    regs += [(f["name"], rss_collector(f), f.get("every", 5)) for f in feeds]
    off = set(p.get("disabled") or [])
    return [r for r in regs if r[0] not in off]
