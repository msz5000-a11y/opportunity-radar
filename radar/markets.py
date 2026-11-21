"""Radar de mercados: acciones de EE. UU. y cripto establecidas que parecen infravaloradas.

Método (como un fondo cuantitativo): valor + calidad + momento en cada activo, descartes «antitrampa» y una señal
técnica de giro para avisar. Registra cada señal en una cartera fantasma para medir si el sistema funciona.
Nunca compra ni vende nada: solo analiza y avisa.

Fuentes gratuitas: Finnhub (cuentas, FINNHUB_API_KEY), Massive (precios, MASSIVE_API_KEY), CoinGecko, DefiLlama,
CoinMetrics Community, alternative.me (miedo y codicia), ApeWisdom (menciones en Reddit) y Tavily (noticias).
Uso: python -m radar.markets [--data data] [--force]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import net, notify, search

MASSIVE = "https://api.massive.com"
MIN_MCAP, MIN_PRICE, MIN_DOLLAR_VOL = 500e6, 5.0, 5e6
FINALISTS = 40
FH_PER_RUN = 300  # empresas consultadas en Finnhub por ejecución (60 por minuto)
SIGNAL_MIN_SCORE = 60
PAPER_DAYS = 90
STABLE = {"usdt", "usdc", "dai", "fdusd", "tusd", "usde", "usds", "pyusd", "usdd", "frax", "gusd", "usdp", "lusd", "eurc",
          "susde", "usd0", "rlusd", "usdy", "buidl", "usdtb", "usdf", "usd1", "bfusd", "usdg", "eurs", "xaut", "paxg", "susds"}
WRAPPED = ("wrapped", "bridged", "staked", "restaked", "liquid staking", "wormhole", "binance-peg", "tokenized")
STATUS: dict = {}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ok(name, n=0, err=None):
    STATUS[name] = {"ok": err is None, "items": n, **({"error": str(err)[:160]} if err else {})}


# ------------------------------------------------------------------ indicadores
def sma(xs, n, end=None):
    end = len(xs) if end is None else end + 1
    return sum(xs[end - n:end]) / n if end >= n else None


def rsi(c, n=14):
    if len(c) <= n:
        return None
    gains = [max(0.0, c[i] - c[i - 1]) for i in range(1, len(c))]
    losses = [max(0.0, c[i - 1] - c[i]) for i in range(1, len(c))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + l) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def atr(h, l, c, n=14):
    if len(c) <= n:
        return None
    tr = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    return sum(tr[-n:]) / n


def detect_trigger(c, h=None, l=None, v=None):
    """Señal de giro: recupera la media de 50 sesiones tras semanas por debajo, o rebota en una media de 200 creciente."""
    n = len(c)
    if n < 230:
        return None
    h, l = h or c, l or c
    r = rsi(c) or 0
    last = n - 1
    for k in range(3):
        i = last - k
        if c[i] > sma(c, 50, i) and c[i - 1] <= sma(c, 50, i - 1):
            below = sum(1 for j in range(i - 26, i - 1) if c[j] < sma(c, 50, j))
            vr = None
            if v and sum(v[i - 20:i]) > 0:
                vr = max(v[x] for x in range(i, n)) / (sum(v[i - 20:i]) / 20)
            if below >= 18 and c[last] > sma(c, 50) and r > 50 and (vr is None or vr >= 1.5):
                return {"type": "media50", "text": "Recupera su media de 50 sesiones tras semanas por debajo, con RSI por encima de 50"
                        + (" y volumen alto" if vr else "")}
    s200, s200_old = sma(c, 200), sma(c, 200, last - 20)
    if s200 and s200_old and s200 > s200_old and c[last] > s200 and min(l[-3:]) <= s200 * 1.02 and r > 45:
        return {"type": "media200", "text": "Rebota en su media de 200 sesiones, que va subiendo"}
    return None


def technicals(c, h=None, l=None, v=None, bench=None) -> dict:
    h, l = h or c, l or c
    out = {"close": c[-1], "sma50": sma(c, 50), "sma200": sma(c, 200), "rsi": rsi(c), "atr": atr(h, l, c)}
    out["mom12_1"] = (c[-22] / c[-253] - 1) if len(c) >= 253 and c[-253] > 0 else None
    out["ret3m"] = (c[-1] / c[-64] - 1) if len(c) >= 64 else None
    if bench and len(bench) >= 64 and out["ret3m"] is not None:
        out["rs3m"] = (1 + out["ret3m"]) / (bench[-1] / bench[-64]) - 1
    if v:
        out["dollarVol20"] = sum(c[i] * v[i] for i in range(-20, 0)) / 20
    out["trigger"] = detect_trigger(c, h, l, v)
    a = out["atr"] or (c[-1] * 0.05)
    swing = min(l[-20:])
    stop = min(swing, c[-1] - 2 * a)  # el mínimo reciente, pero nunca a menos de 2 ATR del precio
    out["stop"] = round(stop, 6)
    out["riskPct"] = round((c[-1] - stop) / c[-1] * 100, 1)
    return out


def pct_rank(values: dict, higher_better=True) -> dict:
    """Percentil 0-1 de cada clave entre los valores no nulos."""
    items = sorted((v, k) for k, v in values.items() if v is not None)
    n = len(items)
    if n == 0:
        return {}
    out = {}
    for i, (_, k) in enumerate(items):
        p = i / (n - 1) if n > 1 else 0.5
        out[k] = p if higher_better else 1 - p
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


# ------------------------------------------------------------------ fuentes
_massive_last = [0.0]


def massive(path: str, params: dict | None = None) -> dict:
    """Massive (antes Polygon.io), plan gratuito: 5 llamadas/minuto y datos de cierre del día anterior."""
    key = os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY")
    if not key:
        raise RuntimeError("falta MASSIVE_API_KEY")
    p = {**(params or {}), "apiKey": key}
    for attempt in range(2):
        wait = 12.6 - (time.time() - _massive_last[0])
        if wait > 0:
            time.sleep(wait)
        _massive_last[0] = time.time()
        try:
            return net.request("GET", MASSIVE + path, params=p, timeout=60, retries=1).json()
        except Exception as e:  # noqa: BLE001
            if "429" in str(e) and attempt == 0:
                time.sleep(62)
                continue
            raise RuntimeError(str(e).replace(key, "***"))
    return {}


def massive_tickers() -> dict:
    """Acciones ordinarias de NYSE/Nasdaq (Massive, referencia gratuita): {TICKER: nombre}."""
    out, cursor, pages = {}, None, 0
    while pages < 8:
        params = {"market": "stocks", "type": "CS", "active": "true", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        res = massive("/v3/reference/tickers", params)
        for t in res.get("results") or []:
            if t.get("primary_exchange") in ("XNYS", "XNAS", "XASE", "ARCX", "BATS"):
                out[t["ticker"].upper()] = t.get("name") or t["ticker"]
        nxt = res.get("next_url") or ""
        cursor = nxt.split("cursor=")[1].split("&")[0] if "cursor=" in nxt else None
        pages += 1
        if not cursor:
            break
    return out


def grouped_daily() -> tuple[str | None, dict]:
    """Cierre de todas las acciones de EE. UU. del último día disponible (una llamada)."""
    d = now_utc().date()
    for back in range(1, 7):
        day = d - timedelta(days=back)
        if day.weekday() >= 5:
            continue
        res = massive(f"/v2/aggs/grouped/locale/us/market/stocks/{day.isoformat()}", {"adjusted": "true"})
        rows = res.get("results") or []
        if rows:
            return day.isoformat(), {r["T"]: r for r in rows if r.get("T")}
    return None, {}


def bars(ticker: str, days: int = 400) -> dict | None:
    to = now_utc().date()
    res = massive(f"/v2/aggs/ticker/{ticker}/range/1/day/{(to - timedelta(days=days)).isoformat()}/{to.isoformat()}",
                  {"adjusted": "true", "sort": "asc", "limit": 500})
    rows = res.get("results") or []
    if len(rows) < 60:
        return None
    return {"c": [r["c"] for r in rows], "h": [r["h"] for r in rows], "l": [r["l"] for r in rows], "v": [r.get("v", 0) for r in rows]}


_fh_last = [0.0]


def finnhub(path: str, params: dict) -> dict:
    """Finnhub, plan gratuito (60 llamadas/minuto, solo EE. UU.)."""
    key = os.environ.get("FINNHUB_API_KEY")
    for attempt in range(2):
        wait = 1.05 - (time.time() - _fh_last[0])
        if wait > 0:
            time.sleep(wait)
        _fh_last[0] = time.time()
        try:
            return net.request("GET", "https://finnhub.io/api/v1" + path, params={**params, "token": key}, timeout=30, retries=1).json()
        except Exception as e:  # noqa: BLE001
            if "429" in str(e) and attempt == 0:
                time.sleep(61)
                continue
            raise RuntimeError(str(e).replace(key or "#", "***"))
    return {}


FH_FIELDS = {"mcap": ["marketCapitalization"], "pe": ["peTTM", "peBasicExclExtraTTM", "peAnnual"],
             "pb": ["pbQuarterly", "pbAnnual"], "pfcf": ["pfcfShareTTM", "pfcfShareAnnual"],
             "evFcf": ["currentEv/freeCashFlowTTM", "currentEv/freeCashFlowAnnual"],
             "roi": ["roiTTM", "roiAnnual"], "roa": ["roaTTM", "roaRfy"], "gm": ["grossMarginTTM", "grossMarginAnnual"],
             "om": ["operatingMarginTTM", "operatingMarginAnnual"], "nm": ["netProfitMarginTTM", "netProfitMarginAnnual"],
             "cr": ["currentRatioQuarterly", "currentRatioAnnual"], "de": ["totalDebt/totalEquityQuarterly", "totalDebt/totalEquityAnnual"],
             "cov": ["netInterestCoverageTTM", "netInterestCoverageAnnual"], "revG": ["revenueGrowthTTMYoy"], "epsG": ["epsGrowthTTMYoy"]}
SERIES = ("roa", "currentRatio", "grossMargin", "totalDebtToEquity")


def fh_metrics(sym: str) -> dict:
    d = finnhub("/stock/metric", {"symbol": sym, "metric": "all"})
    m = d.get("metric") or {}
    out = {k: next((m[f] for f in fs if isinstance(m.get(f), (int, float))), None) for k, fs in FH_FIELDS.items()}
    ann = (d.get("series") or {}).get("annual") or {}
    for s in SERIES:
        vals = [x.get("v") for x in (ann.get(s) or [])[:2] if isinstance(x.get("v"), (int, float))]
        if len(vals) == 2:
            out[s + "Y"], out[s + "P"] = vals[0], vals[1]
    return out


def ape(kind: str) -> dict:
    """Menciones en Reddit (ApeWisdom): {SIMBOLO: {...}}."""
    try:
        r = net.request("GET", f"https://apewisdom.io/api/v1.0/filter/{kind}/page/1", timeout=20, retries=1).json()
        out = {str(x.get("ticker", "")).upper(): {"mentions": x.get("mentions"), "rank": x.get("rank"),
                                                  "mentions24hAgo": x.get("mentions_24h_ago"), "rank24hAgo": x.get("rank_24h_ago")}
               for x in r.get("results", []) if x.get("ticker")}
        _ok(f"apewisdom_{kind}", len(out))
        return out
    except Exception as e:  # noqa: BLE001
        _ok(f"apewisdom_{kind}", 0, e)
        return {}


def news(query: str) -> list[dict]:
    return [{"title": x["title"], "url": x["url"], "date": x.get("date")}
            for x in search.tavily(query, max_results=3, time_range="week", topic="news")]


# ------------------------------------------------------------------ acciones
def fscore_lite(m: dict) -> tuple[int, list[str]]:
    """Calidad tipo Piotroski aproximada con los datos gratuitos de Finnhub (9 puntos)."""
    def gt(a, b):
        return a is not None and b is not None and a > b
    checks = [("beneficio positivo", (m.get("nm") or 0) > 0), ("caja libre positiva", (m.get("pfcf") or 0) > 0),
              ("rentabilidad sobre activos positiva", (m.get("roa") or 0) > 0),
              ("rentabilidad sobre activos al alza", gt(m.get("roaY"), m.get("roaP"))),
              ("liquidez corriente al alza", gt(m.get("currentRatioY"), m.get("currentRatioP"))),
              ("margen bruto al alza", gt(m.get("grossMarginY"), m.get("grossMarginP"))),
              ("menos deuda", gt(m.get("totalDebtToEquityP"), m.get("totalDebtToEquityY"))),
              ("ventas al alza", (m.get("revG") or 0) > 0), ("beneficio por acción al alza", (m.get("epsG") or 0) > 0)]
    pts = [label for label, ok in checks if ok]
    return len(pts), pts


def score_stocks(cache: dict, prices: dict) -> tuple[list[dict], dict]:
    """Etapa A: descartes antitrampa y nota de valor + calidad."""
    rows = []
    for sym, entry in cache.items():
        m, p = entry.get("m") or {}, prices.get(sym)
        if not p or not m.get("mcap"):
            continue
        price, dv = p["c"], p["c"] * p.get("v", 0)
        if price < MIN_PRICE or dv < MIN_DOLLAR_VOL or m["mcap"] * 1e6 < MIN_MCAP:
            continue
        if m.get("gm") is None and m.get("cr") is None:
            continue  # sin margen bruto ni liquidez corriente: casi siempre banco o aseguradora (se valoran aparte)
        r = {**m, "ticker": sym, "name": entry.get("name") or sym, "price": price, "mcap": m["mcap"] * 1e6}
        r["fscore"], r["fscoreDetail"] = fscore_lite(m)
        fails = []
        if (m.get("nm") is not None and m["nm"] < 0) and (m.get("pfcf") is not None and m["pfcf"] < 0):
            fails.append("pierde dinero y quema caja")
        if r["fscore"] <= 3:
            fails.append("calidad baja (3 puntos o menos de 9)")
        if m.get("de") is not None and m["de"] > 2.5:
            fails.append("deuda de más de 2,5 veces su patrimonio")
        if m.get("cov") is not None and m["cov"] < 2:
            fails.append("apenas cubre los intereses de su deuda")
        if m.get("revG") is not None and m["revG"] < -20:
            fails.append("ventas cayendo más de un 20 %")
        if not (m.get("pe") and m["pe"] > 0):
            fails.append("sin beneficios (PER no válido)")
        r["fails"] = fails
        rows.append(r)
    ok = [r for r in rows if not r["fails"]]
    pv = [pct_rank({r["ticker"]: (r[k] if r.get(k) and r[k] > 0 else None) for r in ok}, False) for k in ("evFcf", "pe", "pb", "pfcf")]
    pq = [pct_rank({r["ticker"]: r.get(k) for r in ok}, True) for k in ("roi", "gm", "om")]
    for r in ok:
        r["value"] = _mean([d.get(r["ticker"]) for d in pv]) or 0
        r["quality"] = _mean([d.get(r["ticker"]) for d in pq] + [r["fscore"] / 9]) or 0
        r["stageA"] = 40 * r["value"] + 35 * r["quality"]
    ok.sort(key=lambda r: -r["stageA"])

    def median(k):
        xs = sorted(r[k] for r in ok if r.get(k) and r[k] > 0)
        return xs[len(xs) // 2] if xs else None
    return ok, {"pe": median("pe"), "pfcf": median("pfcf"), "universe": len(rows), "passed": len(ok)}


def stocks(data_dir: Path) -> dict:
    out = {"enabled": False}
    if not (os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY")):
        _ok("massive", 0, "falta la clave gratuita MASSIVE_API_KEY")
        return out
    if not os.environ.get("FINNHUB_API_KEY"):
        _ok("finnhub", 0, "falta la clave gratuita FINNHUB_API_KEY")
        return out
    try:
        names = massive_tickers()
        _ok("massive_tickers", len(names), None if names else "sin datos")
        date, prices = grouped_daily()
        _ok("massive_grouped", len(prices), None if prices else "sin datos del último día")
    except Exception as e:  # noqa: BLE001
        _ok("massive_grouped", 0, e)
        return out
    if not prices or not names:
        return out
    # Cuentas (Finnhub) con caché rotatoria: hasta FH_PER_RUN empresas al día, refresco semanal
    cp = data_dir / "fund_cache.json"
    cache = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {}
    today = now_utc().date()
    cand = sorted((s for s in names if s in prices and prices[s].get("c", 0) >= MIN_PRICE
                   and prices[s]["c"] * prices[s].get("v", 0) >= MIN_DOLLAR_VOL), key=lambda s: -prices[s]["c"] * prices[s].get("v", 0))
    stale = [s for s in cand if s not in cache or (today - datetime.fromisoformat(cache[s]["at"]).date()).days >= 7]
    fetched, err = 0, None
    for s in stale[:FH_PER_RUN]:
        try:
            cache[s] = {"at": today.isoformat(), "name": names[s], "m": fh_metrics(s)}
            fetched += 1
        except Exception as e:  # noqa: BLE001
            err = e
            if "401" in str(e) or "403" in str(e):
                break
    cache = {s: v for s, v in cache.items() if s in names}
    cp.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _ok("finnhub_metrics", fetched, err if not fetched and err else None)
    ranked, med = score_stocks(cache, prices)
    finalists = ranked[:FINALISTS]
    spy = None
    try:
        spy = bars("SPY")
    except Exception as e:  # noqa: BLE001
        _ok("massive_bars", 0, e)
    hist_ok = 0
    for r in finalists:
        try:
            b = bars(r["ticker"])
        except Exception as e:  # noqa: BLE001
            _ok("massive_bars", hist_ok, e)
            b = None
        if b:
            hist_ok += 1
            r["tech"] = technicals(b["c"], b["h"], b["l"], b["v"], spy["c"] if spy else None)
        try:
            prof = finnhub("/stock/profile2", {"symbol": r["ticker"]})
            r["sector"] = prof.get("finnhubIndustry") or ""
        except Exception:  # noqa: BLE001
            r["sector"] = ""
    _ok("massive_bars", hist_ok)
    fin = [r for r in finalists if r.get("tech") and r.get("sector") not in ("Banking", "Insurance", "Financial Services", "Real Estate")]
    mom = pct_rank({r["ticker"]: r["tech"].get("mom12_1") for r in fin})
    rs = pct_rank({r["ticker"]: r["tech"].get("rs3m") for r in fin})
    val = pct_rank({r["ticker"]: r["value"] for r in fin})
    qual = pct_rank({r["ticker"]: r["quality"] for r in fin})
    def sector_median(sec, k):
        xs = sorted(x[k] for x in ranked if x.get("sector") == sec and x.get(k) and x[k] > 0)
        return xs[len(xs) // 2] if len(xs) >= 3 else None
    items = []
    for r in fin:
        tch = r["tech"]
        m = _mean([mom.get(r["ticker"]), rs.get(r["ticker"]), 1.0 if tch["sma200"] and tch["close"] > tch["sma200"] else 0.0]) or 0
        score = round(40 * val.get(r["ticker"], 0) + 35 * qual.get(r["ticker"], 0) + 25 * m)
        knife = mom.get(r["ticker"], 0.5) < 0.2 and tch["sma200"] and tch["close"] < tch["sma200"]
        fair = []  # valor razonable: vuelta al múltiplo mediano de su sector (solo si hay al menos 3 empresas comparables)
        spe, spf = sector_median(r.get("sector"), "pe"), sector_median(r.get("sector"), "pfcf")
        if spe and r.get("pe"):
            fair.append(tch["close"] * spe / r["pe"])
        if spf and r.get("pfcf") and r["pfcf"] > 0:
            fair.append(tch["close"] * spf / r["pfcf"])
        items.append({
            "symbol": r["ticker"], "name": r["name"], "sector": r.get("sector"), "price": round(tch["close"], 2),
            "mcap": r["mcap"], "score": score, "fallingKnife": bool(knife), "trigger": tch["trigger"],
            "metrics": {"pe": _r(r.get("pe"), 1), "pfcf": _r(r.get("pfcf"), 1), "evFcf": _r(r.get("evFcf"), 1), "pb": _r(r.get("pb"), 2),
                        "roi": _r(r.get("roi"), 1), "gm": _r(r.get("gm"), 1), "om": _r(r.get("om"), 1), "fscore": r["fscore"],
                        "de": _r(r.get("de"), 2), "revG": _r(r.get("revG"), 1)},
            "fscoreDetail": r["fscoreDetail"],
            "tech": {k: _r(tch.get(k), 2) for k in ("sma50", "sma200", "rsi", "stop", "riskPct")} | {
                "mom12_1": _r(tch["mom12_1"] * 100 if tch.get("mom12_1") is not None else None, 1),
                "rs3m": _r(tch["rs3m"] * 100 if tch.get("rs3m") is not None else None, 1)},
            "fairValue": [round(min(fair), 2), round(max(fair), 2)] if fair else None,
        })
    items.sort(key=lambda x: (-(1 if x["trigger"] and not x["fallingKnife"] else 0), -x["score"]))
    regime = None
    if spy:
        regime = {"symbol": "S&P 500 (SPY)", "close": spy["c"][-1], "sma200": _r(sma(spy["c"], 200), 2),
                  "riskOn": bool(sma(spy["c"], 200) and spy["c"][-1] > sma(spy["c"], 200))}
    return {"enabled": True, "priceDate": date, "universe": len(cand), "covered": len(cache), "studied": med["universe"],
            "passed": med["passed"], "medians": {"pe": _r(med["pe"], 1), "pfcf": _r(med["pfcf"], 1)},
            "regime": regime, "items": items, "prices": {k: v["c"] for k, v in prices.items()}}


def _r(x, n):
    return round(x, n) if isinstance(x, (int, float)) else None


# ------------------------------------------------------------------ cripto
def crypto() -> dict:
    try:
        coins = []
        for page in (1, 2):
            coins += net.request("GET", "https://api.coingecko.com/api/v3/coins/markets", timeout=30, retries=3,
                                 params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 150, "page": page}).json()
        _ok("coingecko_markets", len(coins))
    except Exception as e:  # noqa: BLE001
        _ok("coingecko_markets", 0, e)
        return {"enabled": False}
    uni = []
    for c in coins:
        sym, name = str(c.get("symbol", "")).lower(), str(c.get("name", "")).lower()
        if sym in STABLE or any(w in name for w in WRAPPED) or (c.get("total_volume") or 0) < 5e6:
            continue
        if c.get("current_price") and 0.97 < c["current_price"] < 1.03 and (c.get("ath") or 0) < 1.3:
            continue
        circ, tot = c.get("circulating_supply"), c.get("total_supply") or c.get("max_supply")
        c["_circ"] = circ / tot if circ and tot else None
        uni.append(c)
    # Comisiones e ingresos (DefiLlama)
    fees, rev = {}, {}
    try:
        protos = net.request("GET", "https://api.llama.fi/protocols", timeout=60).json()
        gid = {p.get("slug"): p.get("gecko_id") for p in protos if p.get("gecko_id")}
        gid.update({p.get("name"): p.get("gecko_id") for p in protos if p.get("gecko_id")})
        chains = net.request("GET", "https://api.llama.fi/v2/chains", timeout=60).json()
        gid.update({ch.get("name"): ch.get("gecko_id") for ch in chains if ch.get("gecko_id")})
        for dt, target in (("dailyFees", fees), ("dailyRevenue", rev)):
            ov = net.request("GET", "https://api.llama.fi/overview/fees", timeout=60,
                             params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true", "dataType": dt}).json()
            for p in ov.get("protocols", []):
                g = p.get("gecko_id") or gid.get(p.get("slug")) or gid.get(p.get("name")) or gid.get(p.get("displayName"))
                if g and p.get("total30d"):
                    prev = target.get(g, {})
                    target[g] = {"d30": (prev.get("d30") or 0) + p["total30d"], "change1m": p.get("change_1m")}
        _ok("defillama_fees", len(fees))
    except Exception as e:  # noqa: BLE001
        _ok("defillama_fees", len(fees), e)
    # MVRV (CoinMetrics Community)
    mvrv = {}
    try:
        syms = ",".join(c["symbol"].lower() for c in uni[:120])
        r = net.request("GET", "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics", timeout=60, params={
            "assets": syms, "metrics": "CapMVRVCur", "frequency": "1d", "limit_per_asset": 1,
            "ignore_unsupported_errors": "true", "page_size": 1000}).json()
        mvrv = {x["asset"]: float(x["CapMVRVCur"]) for x in r.get("data", []) if x.get("CapMVRVCur")}
        _ok("coinmetrics_mvrv", len(mvrv))
    except Exception as e:  # noqa: BLE001
        _ok("coinmetrics_mvrv", 0, e)
    fng = None
    try:
        x = net.request("GET", "https://api.alternative.me/fng/", params={"limit": 1}, timeout=20).json()["data"][0]
        fng = {"value": int(x["value"]), "label": x.get("value_classification")}
        _ok("fear_greed", 1)
    except Exception as e:  # noqa: BLE001
        _ok("fear_greed", 0, e)
    for c in uni:
        mc = c.get("market_cap") or 0
        f, rv = fees.get(c["id"]), rev.get(c["id"])
        c["_pf"] = mc / (f["d30"] * 365 / 30) if f and f["d30"] > 0 and mc else None
        c["_ps"] = mc / (rv["d30"] * 365 / 30) if rv and rv["d30"] > 0 and mc else None
        c["_growth"] = (f or {}).get("change1m")
        c["_mvrv"] = mvrv.get(c["symbol"].lower())
        c["_disc"] = -(c.get("ath_change_percentage") or 0)
        fails = []
        if c["_circ"] is not None and c["_circ"] < 0.5:
            fails.append("menos del 50 % del suministro en circulación (dilución futura)")
        if c["_pf"] is None and c["_mvrv"] is None:
            fails.append("sin ingresos ni datos en cadena para valorarla")
        c["_fails"] = fails
    ok = [c for c in uni if not c["_fails"]]
    pf, ps = pct_rank({c["id"]: c["_pf"] for c in ok}, False), pct_rank({c["id"]: c["_ps"] for c in ok}, False)
    disc, gr = pct_rank({c["id"]: c["_disc"] for c in ok}), pct_rank({c["id"]: c["_growth"] for c in ok})
    for c in ok:
        mv = c["_mvrv"]
        mvs = None if mv is None else (1.0 if mv < 1 else 0.6 if mv < 2 else 0.3 if mv < 3 else 0.0)
        c["_value"] = _mean([pf.get(c["id"]), ps.get(c["id"]), mvs, disc.get(c["id"])]) or 0
        c["_usage"] = gr.get(c["id"], 0.5)
    ok.sort(key=lambda c: -(35 * c["_value"] + 25 * c["_usage"]))
    fin = ok[:FINALISTS]
    # Historia de precios (DefiLlama, sin clave) para el técnico
    hist, errs = {}, []
    ids = ["coingecko:bitcoin"] + [f"coingecko:{c['id']}" for c in fin if c["id"] != "bitcoin"]
    end = int(now_utc().timestamp())
    variants = [{"end": end, "span": 400, "period": "1d"}, {"end": end, "span": 300, "period": "1d"},
                {"start": end - 400 * 86400, "span": 400, "period": "1d"}]
    import requests as _rq
    for i in range(0, len(ids)):  # máximo 500 puntos por petición: una moneda cada vez
        batch = ids[i]
        for params in variants:
            try:
                r = _rq.get(f"https://coins.llama.fi/chart/{batch}", params=params, timeout=60,
                            headers={"User-Agent": net.UA, "Accept": "application/json"})
                if r.status_code != 200:
                    errs.append(f"{r.status_code} {params}: {r.text[:120]}")
                    continue
                for k, v in (r.json().get("coins") or {}).items():
                    hist[k.split(":", 1)[1]] = [p["price"] for p in v.get("prices", []) if p.get("price")]
                variants = [params] + [x for x in variants if x is not params]
                break
            except Exception as e:  # noqa: BLE001
                errs.append(str(e)[:120])
        time.sleep(0.3)
    _ok("defillama_prices", len(hist), None if hist else ("; ".join(errs[:3]) or "sin datos"))
    btc = hist.get("bitcoin")
    reddit = ape("all-crypto")
    for c in fin:
        h = hist.get(c["id"])
        if h and len(h) >= 60:
            c["_tech"] = technicals(h, bench=btc)
    fin = [c for c in fin if c.get("_tech")]
    rs = pct_rank({c["id"]: c["_tech"].get("rs3m") for c in fin})
    val, use = pct_rank({c["id"]: c["_value"] for c in fin}), pct_rank({c["id"]: c["_usage"] for c in fin})
    contrarian = (100 - fng["value"]) / 100 if fng else 0.5
    items = []
    for c in fin:
        t = c["_tech"]
        tech = _mean([1.0 if t["sma50"] and t["close"] > t["sma50"] else 0.0, 1.0 if t["sma200"] and t["close"] > t["sma200"] else 0.0,
                      rs.get(c["id"]), 1.0 if t["rsi"] and 40 <= t["rsi"] <= 65 else 0.4]) or 0
        rd = reddit.get(c["symbol"].upper())
        attention = 0.5
        if rd and rd.get("rank") and rd.get("rank24hAgo"):
            attention = 0.7 if rd["rank"] < rd["rank24hAgo"] else 0.4
        score = round(35 * val.get(c["id"], 0) + 25 * use.get(c["id"], 0.5) + 20 * tech + 20 * _mean([contrarian, attention]))
        knife = t["sma200"] and t["close"] < t["sma200"] and (t.get("rs3m") or 0) < -0.2
        items.append({"symbol": c["symbol"].upper(), "name": c["name"], "id": c["id"], "price": c.get("current_price"),
                      "mcap": c.get("market_cap"), "score": score, "fallingKnife": bool(knife), "trigger": t["trigger"],
                      "metrics": {"pf": _r(c["_pf"], 1), "ps": _r(c["_ps"], 1), "mvrv": _r(c["_mvrv"], 2),
                                  "athDiscount": _r(c["_disc"], 1), "feesGrowth": _r(c["_growth"], 1),
                                  "circulating": _r(c["_circ"] * 100 if c["_circ"] is not None else None, 0)},
                      "tech": {k: _r(t.get(k), 6 if k in ("sma50", "sma200", "stop") else 1) for k in ("sma50", "sma200", "rsi", "stop", "riskPct")}
                      | {"rs3m": _r(t["rs3m"] * 100 if t.get("rs3m") is not None else None, 1)},
                      "reddit": rd})
    items.sort(key=lambda x: (-(1 if x["trigger"] and not x["fallingKnife"] else 0), -x["score"]))
    regime = None
    if btc and len(btc) >= 200:
        regime = {"symbol": "Bitcoin", "close": btc[-1], "sma200": _r(sma(btc, 200), 2), "riskOn": btc[-1] > sma(btc, 200)}
    return {"enabled": True, "universe": len(uni), "passed": len(ok), "fearGreed": fng, "regime": regime, "items": items,
            "prices": {c["symbol"].upper(): c.get("current_price") for c in coins}, "btc": btc[-1] if btc else None}


# ------------------------------------------------------------------ cartera fantasma y señales
def update_paper(paper: dict, st: dict, cr: dict, today: str) -> list[dict]:
    """Abre posiciones ficticias con cada señal nueva y actualiza las abiertas. Devuelve las señales nuevas."""
    pos = paper.setdefault("positions", [])
    spx = (st.get("prices") or {}).get("SPY")
    btc = cr.get("btc")
    px = {"accion": st.get("prices") or {}, "cripto": cr.get("prices") or {}}
    bench_now = {"accion": spx, "cripto": btc}
    for p in pos:
        if p["status"] != "abierta":
            continue
        cur = px[p["type"]].get(p["symbol"])
        if not cur:
            continue
        p["last"], p["lastAt"] = cur, today
        p["returnPct"] = round((cur / p["entry"] - 1) * 100, 2)
        if bench_now[p["type"]] and p.get("benchEntry"):
            p["benchPct"] = round((bench_now[p["type"]] / p["benchEntry"] - 1) * 100, 2)
        age = (datetime.fromisoformat(today) - datetime.fromisoformat(p["date"])).days
        if cur <= p["stop"] or age >= PAPER_DAYS:
            p["status"], p["closedAt"], p["exitReason"] = "cerrada", today, ("stop" if cur <= p["stop"] else f"{PAPER_DAYS} días")
    recent = {(p["type"], p["symbol"]) for p in pos
              if p["status"] == "abierta" or (datetime.fromisoformat(today) - datetime.fromisoformat(p["date"])).days < 30}
    new = []
    for typ, block in (("accion", st), ("cripto", cr)):
        reg = block.get("regime") or {}
        for it in block.get("items", []):
            min_score = SIGNAL_MIN_SCORE if reg.get("riskOn", True) else SIGNAL_MIN_SCORE + 10
            if not it.get("trigger") or it.get("fallingKnife") or it["score"] < min_score or (typ, it["symbol"]) in recent:
                continue
            p = {"id": f"{typ}-{it['symbol']}-{today}", "type": typ, "symbol": it["symbol"], "name": it["name"], "date": today,
                 "entry": it["price"], "stop": it["tech"]["stop"], "score": it["score"], "trigger": it["trigger"]["text"],
                 "benchEntry": bench_now[typ], "status": "abierta", "returnPct": 0.0}
            pos.append(p)
            new.append(p)
    closed = [p for p in pos if p["status"] == "cerrada"]
    allp = [p for p in pos if p.get("returnPct") is not None]
    paper["summary"] = {"signals": len(pos), "open": len(pos) - len(closed), "closed": len(closed),
                        "avgReturn": _r(_mean([p["returnPct"] for p in allp]), 2),
                        "avgBench": _r(_mean([p.get("benchPct") for p in allp]), 2),
                        "hitRate": _r(100 * sum(1 for p in closed if p["returnPct"] > 0) / len(closed), 0) if closed else None}
    paper["positions"] = pos[-200:]
    return new


def run(data_dir: Path, force: bool = False) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    prev_p = data_dir / "markets.json"
    prev = json.loads(prev_p.read_text(encoding="utf-8")) if prev_p.exists() else {}
    t = now_utc()
    last = prev.get("generatedAt")
    if not force and last and t - datetime.fromisoformat(last.replace("Z", "+00:00")) < timedelta(hours=20):
        print("Mercados: ya se actualizó hace menos de 20 h")
        return {"skipped": True}
    STATUS.clear()
    st = stocks(data_dir)
    cr = crypto()
    reddit = ape("all-stocks") if st.get("enabled") else {}
    for it in st.get("items", []):
        it["reddit"] = reddit.get(it["symbol"])
    today = t.date().isoformat()
    paper_p = data_dir / "paper.json"
    paper = json.loads(paper_p.read_text(encoding="utf-8")) if paper_p.exists() else {}
    new = update_paper(paper, st, cr, today)
    for p in new[:5]:  # noticias solo de las señales nuevas (ahorra cupo de búsqueda)
        q = f"{p['name']} {'stock' if p['type'] == 'accion' else 'crypto'}"
        n = news(q)
        block = st if p["type"] == "accion" else cr
        for it in block.get("items", []):
            if it["symbol"] == p["symbol"]:
                it["news"] = n
    out = {"generatedAt": iso(t), "stocks": {k: v for k, v in st.items() if k != "prices"},
           "crypto": {k: v for k, v in cr.items() if k not in ("prices", "btc")}, "status": STATUS,
           "paperSummary": paper.get("summary"), "newSignals": [p["id"] for p in new]}
    prev_p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    paper_p.write_text(json.dumps(paper, ensure_ascii=False, indent=1), encoding="utf-8")
    app = os.environ.get("APP_URL", "")
    for p in new[:3]:
        notify.send(f"📈 Señal: {p['symbol']} ({'acción' if p['type'] == 'accion' else 'cripto'})",
                    f"{p['name']}: parece infravalorada y {p['trigger'].lower()}. Nota {p['score']}/100. "
                    f"Stop orientativo {p['stop']} (si cae ahí, la idea se invalida). No es asesoramiento financiero.",
                    priority=4, tags=["chart_with_upwards_trend"], click=(app + "#mercados") if app else None)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    out = run(Path(a.data), a.force)
    if not out.get("skipped"):
        print(json.dumps({"status": out["status"], "señales": out["newSignals"],
                          "acciones": len(out["stocks"].get("items", [])), "cripto": len(out["crypto"].get("items", []))},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
