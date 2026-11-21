"""Radar de mercados: acciones de EE. UU. y cripto establecidas que parecen infravaloradas.

Método (como un fondo cuantitativo): valor + calidad + momento en cada activo, descartes «antitrampa» y una señal
técnica de giro para avisar. Registra cada señal en una cartera fantasma para medir si el sistema funciona.
Nunca compra ni vende nada: solo analiza y avisa.

Fuentes gratuitas: SEC EDGAR (cuentas), Massive (precios, clave gratuita MASSIVE_API_KEY), CoinGecko, DefiLlama,
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

SEC_HEADERS = {"User-Agent": "OpportunityRadar msz5000-a11y@users.noreply.github.com", "Accept": "application/json"}
MASSIVE = "https://api.massive.com"
MIN_MCAP, MIN_PRICE, MIN_DOLLAR_VOL = 500e6, 5.0, 5e6
FINALISTS = 40
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
    stop = max(swing, c[-1] - 2 * a)
    if stop >= c[-1] * 0.995:
        stop = min(swing, c[-1] - 2 * a)
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


def sec_json(url: str):
    import requests as _rq
    r = _rq.get(url, headers={**SEC_HEADERS, "Accept-Encoding": "gzip, deflate"}, timeout=90)
    time.sleep(0.12)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}")
    return r.json()


def massive_tickers() -> dict:
    """Plan B si la SEC no deja descargar su lista: tickers de acciones comunes con su CIK (Massive)."""
    out, cursor, pages = {}, None, 0
    while pages < 8:
        params = {"market": "stocks", "type": "CS", "active": "true", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        res = massive("/v3/reference/tickers", params)
        for t in res.get("results") or []:
            if t.get("cik") and t.get("primary_exchange") in ("XNYS", "XNAS", "XASE", "ARCX", "BATS"):
                out[t["ticker"].upper()] = (int(t["cik"]), t.get("name") or t["ticker"])
        nxt = res.get("next_url") or ""
        cursor = nxt.split("cursor=")[1].split("&")[0] if "cursor=" in nxt else None
        pages += 1
        if not cursor:
            break
    return out


def frames(concepts: list[str], period: str, unit: str = "USD") -> dict:
    """Valor por CIK de la primera etiqueta XBRL disponible (SEC EDGAR, todo el mercado en una llamada)."""
    out: dict = {}
    for c in concepts:
        try:
            data = sec_json(f"https://data.sec.gov/api/xbrl/frames/us-gaap/{c}/{unit}/{period}.json").get("data", [])
        except Exception as e:  # noqa: BLE001
            STATUS.setdefault("sec_frames_errors", {"ok": False, "items": 0, "error": str(e)[:160]})
            continue
        for r in data:
            if r.get("val") is not None:
                out.setdefault(int(r["cik"]), float(r["val"]))
    return out


DURATION = {"rev": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
            "gp": ["GrossProfit"], "ebit": ["OperatingIncomeLoss"], "ni": ["NetIncomeLoss"],
            "cfo": ["NetCashProvidedByUsedInOperatingActivities"], "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
            "da": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"]}
INSTANT = {"assets": ["Assets"], "ca": ["AssetsCurrent"], "cl": ["LiabilitiesCurrent"], "liab": ["Liabilities"],
           "eq": ["StockholdersEquity"], "re": ["RetainedEarningsAccumulatedDeficit"],
           "cash": ["CashAndCashEquivalentsAtCarryingValue"], "ltd": ["LongTermDebtNoncurrent", "LongTermDebt"],
           "std": ["DebtCurrent", "LongTermDebtCurrent"]}


def fundamentals(year: int) -> dict:
    """{cik: {"y": {...}, "p": {...}}} con el último año fiscal completo (y) y el anterior (p)."""
    out: dict = {}
    for tag, yr in (("y", year), ("p", year - 1)):
        for k, cs in DURATION.items():
            for cik, v in frames(cs, f"CY{yr}").items():
                out.setdefault(cik, {"y": {}, "p": {}})[tag][k] = v
        for cik, v in frames(["WeightedAverageNumberOfDilutedSharesOutstanding"], f"CY{yr}", "shares").items():
            out.setdefault(cik, {"y": {}, "p": {}})[tag]["shares"] = v
        for k, cs in INSTANT.items():
            for cik, v in frames(cs, f"CY{yr}Q4I").items():
                out.setdefault(cik, {"y": {}, "p": {}})[tag][k] = v
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
def score_stocks(fund: dict, prices: dict, tickers: dict) -> tuple[list[dict], dict]:
    """Etapa A: descartes antitrampa y nota de valor + calidad con las cuentas y el último cierre."""
    by_cik: dict = {}
    for t, (cik, name) in tickers.items():
        p = prices.get(t)
        if p and p.get("c") and p.get("v"):
            dv = p["c"] * p["v"]
            if cik not in by_cik or dv > by_cik[cik]["dv"]:
                by_cik[cik] = {"ticker": t, "name": name, "price": p["c"], "dv": dv}
    rows = []
    for cik, q in by_cik.items():
        f = fund.get(cik)
        if not f:
            continue
        y, p = f["y"], f["p"]
        sh, price = y.get("shares"), q["price"]
        if not sh or price < MIN_PRICE or q["dv"] < MIN_DOLLAR_VOL:
            continue
        mcap = price * sh
        if mcap < MIN_MCAP:
            continue
        if y.get("gp") is None and y.get("ca") is None:
            continue  # sin margen bruto ni activo corriente: casi siempre banco o aseguradora (se valoran aparte)
        ta, ebit = y.get("assets"), y.get("ebit")
        debt = (y.get("ltd") or 0) + (y.get("std") or 0)
        cash = y.get("cash") or 0
        ev = mcap + debt - cash
        fcf = (y["cfo"] - (y.get("capex") or 0)) if y.get("cfo") is not None else None
        fcf_p = (p["cfo"] - (p.get("capex") or 0)) if p.get("cfo") is not None else None
        eq = y.get("eq")
        liab = y.get("liab") if y.get("liab") is not None else ((ta - eq) if ta and eq is not None else None)
        ebitda = (ebit + (y.get("da") or 0)) if ebit is not None else None
        r = {"cik": cik, "ticker": q["ticker"], "name": q["name"], "price": price, "mcap": mcap, "ev": ev,
             "shares": sh, "debt": debt, "cash": cash, "ebit": ebit, "fcf": fcf,
             "evEbit": ev / ebit if ebit and ebit > 0 and ev > 0 else None,
             "fcfYield": fcf / ev if fcf is not None and ev > 0 else None,
             "pb": mcap / eq if eq and eq > 0 else None,
             "roic": ebit * 0.79 / (eq + debt - cash) if ebit is not None and eq is not None and (eq + debt - cash) > 0 else None,
             "gpa": y["gp"] / ta if y.get("gp") is not None and ta else None,
             "ndEbitda": (debt - cash) / ebitda if ebitda and ebitda > 0 else None,
             "dilution": sh / p["shares"] - 1 if p.get("shares") else None}
        # Altman Z (no financieras)
        if ta and liab and y.get("ca") is not None and y.get("cl") is not None and ebit is not None and y.get("rev") is not None:
            r["altmanZ"] = (1.2 * (y["ca"] - y["cl"]) / ta + 1.4 * (y.get("re") or 0) / ta + 3.3 * ebit / ta
                            + 0.6 * mcap / liab + 1.0 * y["rev"] / ta)
        r["fscore"], r["fscoreDetail"] = fscore(y, p)
        fails = []
        if r.get("altmanZ") is not None and r["altmanZ"] < 1.8:
            fails.append("riesgo de quiebra (Altman Z < 1,8)")
        if r["fscore"] <= 3:
            fails.append("F-score de 3 o menos")
        if fcf is not None and fcf < 0 and fcf_p is not None and fcf_p < 0:
            fails.append("caja libre negativa dos años")
        if r["dilution"] is not None and r["dilution"] > 0.10:
            fails.append("dilución de más del 10 %")
        if r["ndEbitda"] is not None and r["ndEbitda"] > 4:
            fails.append("deuda neta de más de 4 veces el EBITDA")
        if r["evEbit"] is None:
            fails.append("sin beneficio operativo positivo")
        r["fails"] = fails
        rows.append(r)
    ok = [r for r in rows if not r["fails"]]
    pv = [pct_rank({r["cik"]: r[k] for r in ok}, hb) for k, hb in (("evEbit", False), ("fcfYield", True), ("pb", False))]
    pq = [pct_rank({r["cik"]: r[k] for r in ok}, True) for k in ("roic", "gpa")]
    for r in ok:
        r["value"] = _mean([d.get(r["cik"]) for d in pv]) or 0
        r["quality"] = _mean([d.get(r["cik"]) for d in pq] + [r["fscore"] / 9]) or 0
        r["stageA"] = 35 * r["value"] + 30 * r["quality"]
    ok.sort(key=lambda r: -r["stageA"])
    ev_ebits = sorted(r["evEbit"] for r in ok if r["evEbit"])
    fcfys = sorted(r["fcfYield"] for r in ok if r.get("fcfYield") and r["fcfYield"] > 0)
    med = {"evEbit": ev_ebits[len(ev_ebits) // 2] if ev_ebits else None, "fcfYield": fcfys[len(fcfys) // 2] if fcfys else None,
           "universe": len(rows), "passed": len(ok)}
    return ok, med


def fscore(y: dict, p: dict) -> tuple[int, list[str]]:
    """Piotroski (9 puntos). Si falta un dato, ese punto no suma."""
    pts = []

    def g(d, k):
        return d.get(k)

    ta, tap = g(y, "assets"), g(p, "assets")
    roa = y["ni"] / ta if g(y, "ni") is not None and ta else None
    roap = p["ni"] / tap if g(p, "ni") is not None and tap else None
    checks = [
        ("beneficio positivo", roa is not None and roa > 0),
        ("caja operativa positiva", (g(y, "cfo") or 0) > 0),
        ("rentabilidad sobre activos al alza", roa is not None and roap is not None and roa > roap),
        ("caja operativa mayor que el beneficio", g(y, "cfo") is not None and g(y, "ni") is not None and y["cfo"] > y["ni"]),
        ("menos deuda a largo plazo", ta and tap and (g(y, "ltd") or 0) / ta <= (g(p, "ltd") or 0) / tap),
        ("liquidez corriente al alza", all(g(d, k) for d in (y, p) for k in ("ca", "cl")) and y["ca"] / y["cl"] > p["ca"] / p["cl"]),
        ("sin emitir acciones", g(y, "shares") and g(p, "shares") and y["shares"] <= p["shares"] * 1.005),
        ("margen bruto al alza", all(g(d, k) for d in (y, p) for k in ("gp", "rev")) and y["gp"] / y["rev"] > p["gp"] / p["rev"]),
        ("rotación de activos al alza", all(g(d, k) for d in (y, p) for k in ("rev", "assets")) and y["rev"] / ta > p["rev"] / tap),
    ]
    for label, okk in checks:
        if okk:
            pts.append(label)
    return len(pts), pts


def stocks(data_dir: Path) -> dict:
    out = {"enabled": False}
    if not (os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY")):
        _ok("massive", 0, "falta la clave gratuita MASSIVE_API_KEY")
        return out
    tickers = {}
    try:
        tk = sec_json("https://www.sec.gov/files/company_tickers_exchange.json")
        idx = {k: i for i, k in enumerate(tk["fields"])}
        tickers = {r[idx["ticker"]].upper().replace("-", "."): (int(r[idx["cik"]]), r[idx["name"]]) for r in tk["data"]
                   if r[idx["exchange"]] in ("NYSE", "Nasdaq") and r[idx["ticker"]]}
        _ok("sec_tickers", len(tickers))
    except Exception as e:  # noqa: BLE001
        _ok("sec_tickers", 0, e)
    if not tickers:
        try:
            tickers = massive_tickers()
            _ok("massive_tickers", len(tickers), None if tickers else "sin datos")
        except Exception as e:  # noqa: BLE001
            _ok("massive_tickers", 0, e)
    if not tickers:
        return out
    try:
        date, prices = grouped_daily()
        _ok("massive_grouped", len(prices), None if prices else "sin datos del último día")
    except Exception as e:  # noqa: BLE001
        _ok("massive_grouped", 0, e)
        return out
    if not prices:
        return out
    t = now_utc()
    year = t.year - 1 if t.month >= 4 else t.year - 2
    fund = fundamentals(year)
    _ok("sec_frames", len(fund), None if fund else "sin datos de cuentas")
    ranked, med = score_stocks(fund, prices, tickers)
    # Etapa B: sector (SEC), historia de precios (Massive) y técnico
    finalists = []
    for r in ranked[:FINALISTS + 25]:
        if len(finalists) >= FINALISTS:
            break
        try:
            sub = sec_json(f"https://data.sec.gov/submissions/CIK{r['cik']:010d}.json")
            sic = int(sub.get("sic") or 0)
            r["sector"] = sub.get("sicDescription") or ""
        except Exception:  # noqa: BLE001
            sic, r["sector"] = 0, ""
        if 6000 <= sic <= 6799:
            continue  # financieras y REIT: sus cuentas no encajan con EV/EBIT
        finalists.append(r)
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
    _ok("massive_bars", hist_ok)
    fin = [r for r in finalists if r.get("tech")]
    mom = pct_rank({r["cik"]: r["tech"].get("mom12_1") for r in fin})
    rs = pct_rank({r["cik"]: r["tech"].get("rs3m") for r in fin})
    buy = pct_rank({r["cik"]: (-r["dilution"] if r.get("dilution") is not None else None) for r in fin})
    val = pct_rank({r["cik"]: r["value"] for r in fin})
    qual = pct_rank({r["cik"]: r["quality"] for r in fin})
    items = []
    for r in fin:
        tch = r["tech"]
        m = _mean([mom.get(r["cik"]), rs.get(r["cik"]), 1.0 if tch["sma200"] and tch["close"] > tch["sma200"] else 0.0]) or 0
        score = round(35 * val.get(r["cik"], 0) + 30 * qual.get(r["cik"], 0) + 20 * m + 15 * buy.get(r["cik"], 0.5))
        knife = mom.get(r["cik"], 0.5) < 0.2 and tch["sma200"] and tch["close"] < tch["sma200"]
        fair = []
        if med["evEbit"] and r["ebit"]:
            fair.append((med["evEbit"] * r["ebit"] - r["debt"] + r["cash"]) / r["shares"])
        if med["fcfYield"] and r.get("fcf") and r["fcf"] > 0:
            fair.append((r["fcf"] / med["fcfYield"] - r["debt"] + r["cash"]) / r["shares"])
        fair = [x for x in fair if x > 0]
        items.append({
            "symbol": r["ticker"], "name": r["name"], "sector": r.get("sector"), "price": round(tch["close"], 2),
            "mcap": r["mcap"], "score": score, "fallingKnife": bool(knife), "trigger": tch["trigger"],
            "metrics": {"evEbit": _r(r["evEbit"], 1), "fcfYield": _r(r["fcfYield"] * 100 if r["fcfYield"] is not None else None, 1),
                        "pb": _r(r["pb"], 2), "roic": _r(r["roic"] * 100 if r["roic"] is not None else None, 1),
                        "gpa": _r(r["gpa"] * 100 if r["gpa"] is not None else None, 1), "fscore": r["fscore"],
                        "altmanZ": _r(r.get("altmanZ"), 2), "ndEbitda": _r(r["ndEbitda"], 2),
                        "dilution": _r(r["dilution"] * 100 if r["dilution"] is not None else None, 1)},
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
    return {"enabled": True, "priceDate": date, "fiscalYear": year, "universe": med["universe"], "passed": med["passed"],
            "medians": {"evEbit": _r(med["evEbit"], 1), "fcfYield": _r((med["fcfYield"] or 0) * 100, 1)},
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
