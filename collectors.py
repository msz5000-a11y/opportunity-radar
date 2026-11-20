"""Conectores de fuentes públicas. Cada función devuelve (items, estado) y nunca lanza excepciones."""
from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from . import net

DEX = "https://api.dexscreener.com"
GT = "https://api.geckoterminal.com/api/v2"
CG = "https://api.coingecko.com/api/v3"

EVM_CHAIN_IDS = {"ethereum": 1, "eth": 1, "bsc": 56, "base": 8453, "arbitrum": 42161, "polygon": 137,
                 "polygon_pos": 137, "avalanche": 43114, "avax": 43114, "optimism": 10}


def _status(ok: bool, items: int = 0, error: str | None = None) -> dict:
    return {"ok": ok, "items": items, "error": error, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _safe(fn):
    def wrapper(*a, **kw):
        try:
            items = fn(*a, **kw)
            return items, _status(True, len(items))
        except Exception as e:  # cualquier fallo de una fuente se registra y se sigue
            return [], _status(False, 0, str(e)[:200])
    wrapper.__name__ = fn.__name__
    return wrapper


def fx_usd_eur():
    """Tipo de cambio de referencia del BCE vía Frankfurter (gratuito, sin clave)."""
    try:
        d = net.get_json("https://api.frankfurter.app/latest?from=USD&to=EUR")
        return float(d["rates"]["EUR"]), _status(True, 1)
    except Exception as e:
        return None, _status(False, 0, str(e)[:150])


# ------------------------------------------------------------------ cripto
def _pair_to_market(p: dict) -> dict:
    created = p.get("pairCreatedAt")
    age_h = (time.time() * 1000 - created) / 3_600_000 if created else None
    tx = (p.get("txns") or {}).get("h24") or {}
    return {
        "chain": p.get("chainId"), "tokenAddress": (p.get("baseToken") or {}).get("address"),
        "symbol": (p.get("baseToken") or {}).get("symbol"), "name": (p.get("baseToken") or {}).get("name"),
        "priceUsd": float(p["priceUsd"]) if p.get("priceUsd") else None,
        "liquidityUsd": (p.get("liquidity") or {}).get("usd"), "volume24hUsd": (p.get("volume") or {}).get("h24"),
        "fdvUsd": p.get("fdv"), "mcapUsd": p.get("marketCap"), "ageHours": round(age_h, 1) if age_h else None,
        "buys24h": tx.get("buys"), "sells24h": tx.get("sells"), "pairUrl": p.get("url"),
        "websites": [w.get("url") for w in (p.get("info") or {}).get("websites") or [] if w.get("url")],
        "socials": [s.get("url") for s in (p.get("info") or {}).get("socials") or [] if s.get("url")],
    }


@_safe
def dexscreener_tokens(limit: int = 4) -> list[dict]:
    """Perfiles y boosts recientes → datos de par → filtro previo anti-basura."""
    seen, addrs = set(), []
    for path in ("/token-profiles/latest/v1", "/token-boosts/top/v1"):
        for t in net.get_json(DEX + path)[:40]:
            key = (t.get("chainId"), t.get("tokenAddress"))
            if key[1] and key not in seen:
                seen.add(key)
                addrs.append(key)
    markets = []
    for i in range(0, min(len(addrs), 60), 30):
        chunk = ",".join(a for _, a in addrs[i:i + 30])
        data = net.get_json(f"{DEX}/latest/dex/tokens/{chunk}")
        best = {}
        for p in data.get("pairs") or []:
            m = _pair_to_market(p)
            k = (m["chain"], m["tokenAddress"])
            if k not in best or (m["liquidityUsd"] or 0) > (best[k]["liquidityUsd"] or 0):
                best[k] = m
        markets += best.values()
    keep = []
    for m in markets:
        liq, age = m["liquidityUsd"] or 0, m["ageHours"] or 0
        vol = m["volume24hUsd"] or 0
        if liq < 50_000 or age < 24:          # casi todos los tokens de <24 h o sin liquidez acaban en cero
            continue
        if liq and vol / liq > 8:             # volumen probablemente artificial
            continue
        if (m["sells24h"] or 0) == 0:          # sin ventas = posible honeypot
            continue
        keep.append(m)
    keep.sort(key=lambda m: (m["volume24hUsd"] or 0) / max(m["liquidityUsd"] or 1, 1) * min((m["liquidityUsd"] or 0) / 1e5, 5), reverse=True)
    return [{"source": "DEX Screener", "category": "cripto", "kind": "token", "title": f"{m['name']} ({m['symbol']})",
             "url": (m["websites"] or [m["pairUrl"]])[0], "market": m, "summary": ""} for m in keep[:limit]]


@_safe
def geckoterminal_trending(limit: int = 3) -> list[dict]:
    data = net.get_json(f"{GT}/networks/trending_pools", headers={"Accept": "application/json;version=20230302"})
    out = []
    for p in data.get("data", [])[:20]:
        a = p.get("attributes") or {}
        base = (((p.get("relationships") or {}).get("base_token") or {}).get("data") or {}).get("id", "")
        chain, _, addr = base.partition("_")
        created = a.get("pool_created_at")
        age = None
        if created:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds() / 3600
        tx = ((a.get("transactions") or {}).get("h24") or {})
        m = {"chain": chain, "tokenAddress": addr, "priceUsd": float(a["base_token_price_usd"]) if a.get("base_token_price_usd") else None,
             "liquidityUsd": float(a["reserve_in_usd"]) if a.get("reserve_in_usd") else None,
             "volume24hUsd": float((a.get("volume_usd") or {}).get("h24") or 0), "fdvUsd": float(a["fdv_usd"]) if a.get("fdv_usd") else None,
             "ageHours": round(age, 1) if age else None, "buys24h": tx.get("buys"), "sells24h": tx.get("sells"),
             "pairUrl": f"https://www.geckoterminal.com/{chain}/pools/{a.get('address')}"}
        if (m["liquidityUsd"] or 0) < 50_000 or (m["ageHours"] or 0) < 24 or (m["sells24h"] or 0) == 0:
            continue
        out.append({"source": "GeckoTerminal", "category": "cripto", "kind": "token", "title": a.get("name", ""),
                    "url": m["pairUrl"], "market": m, "summary": ""})
    return out[:limit]


@_safe
def coingecko_trending(limit: int = 5) -> list[dict]:
    data = net.get_json(f"{CG}/search/trending")
    out = []
    for c in data.get("coins", [])[:15]:
        it = c.get("item") or {}
        rank = it.get("market_cap_rank")
        if rank and rank < 300:  # ya conocidas: no son "tempranas"
            continue
        out.append({"source": "CoinGecko", "category": "cripto", "kind": "token", "title": f"{it.get('name')} ({it.get('symbol')})",
                    "url": f"https://www.coingecko.com/es/monedas/{it.get('id')}", "summary": f"Tendencia en CoinGecko; ranking {rank}",
                    "signals": {"cgRank": rank}})
    return out[:limit]


# ------------------------------------------------------------------ tecnología
@_safe
def hacker_news(limit: int = 6) -> list[dict]:
    since = int(time.time()) - 2 * 86400
    data = net.get_json(f"https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&numericFilters=points>40,created_at_i>{since}&hitsPerPage=30")
    hits = sorted(data.get("hits", []), key=lambda h: h.get("points", 0), reverse=True)
    return [{"source": "Hacker News", "category": "ia_tecnologia", "kind": "producto", "title": h.get("title", "").replace("Show HN: ", ""),
             "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
             "summary": f"Show HN con {h.get('points')} puntos y {h.get('num_comments')} comentarios",
             "signals": {"upvotes": h.get("points"), "comments": h.get("num_comments")},
             "extraSources": [f"https://news.ycombinator.com/item?id={h.get('objectID')}"]} for h in hits[:limit]]


@_safe
def github_rising(limit: int = 5) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    data = net.request("GET", f"https://api.github.com/search/repositories?q=created:>{since}+stars:>150&sort=stars&order=desc&per_page=15",
                       headers=headers).json()
    out = []
    for r in data.get("items", [])[:limit]:
        out.append({"source": "GitHub", "category": "ia_tecnologia", "kind": "proyecto", "title": r["full_name"],
                    "url": r.get("homepage") or r["html_url"], "summary": (r.get("description") or "")[:300],
                    "signals": {"stars": r.get("stargazers_count"), "forks": r.get("forks_count")},
                    "extraSources": [r["html_url"]]})
    return out


def _rss_items(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for it in root.iter("item"):
        items.append({"title": (it.findtext("title") or "").strip(), "url": (it.findtext("link") or "").strip(),
                      "summary": (it.findtext("description") or "").strip()[:400], "date": it.findtext("pubDate")})
    for it in root.findall(".//a:entry", ns):
        link = it.find("a:link", ns)
        items.append({"title": (it.findtext("a:title", default="", namespaces=ns)).strip(),
                      "url": link.get("href") if link is not None else "",
                      "summary": (it.findtext("a:summary", default="", namespaces=ns) or it.findtext("a:content", default="", namespaces=ns) or "")[:400],
                      "date": it.findtext("a:updated", default=None, namespaces=ns)})
    return items


def rss(feeds: list[dict], per_feed: int = 4):
    out, status = [], {}
    for f in feeds:
        try:
            if not net.allowed_by_robots(f["url"]):
                raise net.FetchError("robots.txt no lo permite")
            items = _rss_items(net.request("GET", f["url"]).text)[:per_feed]
            for it in items:
                it["summary"] = re.sub(r"<[^>]+>", " ", it["summary"])
                out.append({"source": f["name"], "category": f["category"], "kind": "noticia", **it})
            status[f["name"]] = _status(True, len(items))
        except Exception as e:
            status[f["name"]] = _status(False, 0, str(e)[:200])
    return out, status


# ------------------------------------------------------------------ seguridad de tokens
def token_security(chain: str, address: str) -> tuple[list[dict], dict]:
    """Devuelve (banderas, datos extra). GoPlus + honeypot.is en EVM, RugCheck en Solana."""
    flags, extra = [], {"checks": []}
    chain = (chain or "").lower()
    try:
        if chain == "solana":
            r = net.get_json(f"https://api.rugcheck.xyz/v1/tokens/{address}/report/summary")
            extra["checks"].append({"tool": "RugCheck", "url": f"https://rugcheck.xyz/tokens/{address}", "score": r.get("score_normalised")})
            for risk in r.get("risks") or []:
                lvl = risk.get("level")
                if lvl in ("danger", "warn"):
                    flags.append({"code": "rugcheck_" + (risk.get("name") or "riesgo").lower().replace(" ", "_")[:30],
                                  "severity": "critica" if lvl == "danger" else "media",
                                  "detail": f"RugCheck: {risk.get('name')} — {risk.get('description') or ''}".strip(" —")})
            if r.get("lpLockedPct") is not None:
                extra["lpLockedPct"] = r.get("lpLockedPct")
        elif chain in EVM_CHAIN_IDS:
            cid = EVM_CHAIN_IDS[chain]
            g = net.get_json(f"https://api.gopluslabs.io/api/v1/token_security/{cid}?contract_addresses={address}")
            info = (g.get("result") or {}).get(address.lower()) or {}
            extra["checks"].append({"tool": "GoPlus", "url": f"https://gopluslabs.io/token-security/{cid}/{address}"})
            def yes(k): return str(info.get(k, "0")) == "1"
            if yes("is_honeypot") or yes("cannot_sell_all"):
                flags.append({"code": "honeypot", "severity": "critica", "detail": "GoPlus: el contrato impide vender (honeypot)."})
            if yes("owner_change_balance") or yes("hidden_owner") or yes("can_take_back_ownership"):
                flags.append({"code": "control_propietario", "severity": "critica", "detail": "GoPlus: el propietario puede alterar saldos o recuperar el control."})
            if yes("is_mintable"):
                flags.append({"code": "mint", "severity": "alta", "detail": "GoPlus: se pueden crear tokens nuevos (dilución)."})
            try:
                st = float(info.get("sell_tax") or 0)
                if st > 0.1:
                    flags.append({"code": "impuesto_venta", "severity": "alta", "detail": f"GoPlus: impuesto de venta del {st * 100:.0f}%."})
            except ValueError:
                pass
            holders = info.get("holders") or []
            top10 = sum(float(h.get("percent") or 0) for h in holders[:10]) * 100
            if holders:
                extra["top10Pct"] = round(top10, 1)
            if info.get("holder_count"):
                extra["holders"] = int(info["holder_count"])
            try:
                hp = net.get_json(f"https://api.honeypot.is/v2/IsHoneypot?address={address}&chainID={cid}")
                extra["checks"].append({"tool": "honeypot.is", "url": f"https://honeypot.is/?address={address}"})
                if (hp.get("honeypotResult") or {}).get("isHoneypot"):
                    flags.append({"code": "honeypot", "severity": "critica", "detail": "honeypot.is: la simulación de venta falla."})
            except Exception as e:
                extra["checks"].append({"tool": "honeypot.is", "error": str(e)[:100]})
        else:
            flags.append({"code": "sin_analisis_contrato", "severity": "media", "detail": f"No hay analizador de contratos para la red {chain}."})
    except Exception as e:
        flags.append({"code": "analisis_contrato_fallido", "severity": "media", "detail": f"No se pudo analizar el contrato: {str(e)[:120]}"})
    return flags, extra
