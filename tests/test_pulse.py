import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from radar import notify, pulse, pulse_rules as R, pulse_sources as S

NOW = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>X</title>
<item><title>Binance will list FooCoin (FOO) with seed tag</title><link>https://ex.com/a?utm_source=x</link>
<description><![CDATA[<p>Binance announced it will list FOO.</p>]]></description><pubDate>Mon, 23 Nov 2026 14:30:00 +0000</pubDate></item>
<item><title>Bitcoin price prediction: could hit $200k?</title><link>https://ex.com/b</link><pubDate>Mon, 23 Nov 2026 14:00:00 +0000</pubDate></item>
<item><title>Old story about markets that is quite old</title><link>https://ex.com/c</link><pubDate>Fri, 20 Nov 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""
ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>OpenAI launches free credits program for startups</title>
<link href="https://openai.com/x"/><updated>2026-11-23T13:00:00Z</updated><summary>Startups can apply.</summary></entry></feed>"""


def ctx(state=None, **kw):
    return S.Ctx(NOW, state if state is not None else {}, {"profile": {"region": "es"}}, **kw)


def test_parse_feed_rss_and_atom():
    a = S.parse_feed(RSS)
    assert len(a) == 3 and a[0]["url"].startswith("https://ex.com/a") and "Binance" in a[0]["title"]
    b = S.parse_feed(ATOM)
    assert b[0]["url"] == "https://openai.com/x" and b[0]["date"].startswith("2026-11-23")


def test_classify_intents_and_noise():
    c = R.classify("Binance will list FooCoin (FOO)", "", "cripto")
    assert c["cat"] == "lanzamientos" and "cripto" in c["also"] and c["opp"] >= 2 and "listado" in c["tags"]
    assert R.classify("Bitcoin price prediction: could hit $200k?", "", "cripto")["noise"]
    g = R.classify("Abierta la convocatoria de ayudas para emprendedores digitales", "", "bolsa")
    assert g["cat"] == "startups" and g["opp"] == 3
    a = R.classify("New airdrop: protocol launches points program for early users", "", "cripto")
    assert a["opp"] == 3 and a["cat"] == "lanzamientos"


def test_rss_collector_filters_noise_and_old(monkeypatch):
    class Resp:
        text = RSS
    monkeypatch.setattr(S, "fetch", lambda *a, **k: Resp())
    out = S.rss_collector({"name": "CoinDesk", "url": "https://x/rss", "cat": "cripto"})(ctx())
    assert len(out) == 1
    it = out[0]
    assert it["cat"] == "lanzamientos" and it["kind"] == "news" and it["s"] >= 50 and it["id"].startswith("n:")
    assert it["pub"] == "2026-11-23T14:30:00Z"


def test_gnews_title_suffix_and_source(monkeypatch):
    xml = """<rss><channel><item><title>Startup X raises $10M seed round - TechCrunch</title><link>https://news.google.com/rss/articles/abc</link>
    <pubDate>Mon, 23 Nov 2026 14:00:00 GMT</pubDate><source url="https://techcrunch.com">TechCrunch</source></item></channel></rss>"""

    class Resp:
        text = xml
    monkeypatch.setattr(S, "fetch", lambda *a, **k: Resp())
    out = S.rss_collector({"name": "Google News", "url": "https://news.google.com/rss/search?q=x", "cat": "startups", "gnews": True})(ctx())
    assert out[0]["title"] == "Startup X raises $10M seed round" and out[0]["src"] == "TechCrunch" and out[0]["via"] == "Google News"


def coin(cid, sym, ch24, ch1=0.5, mcap=2e9, vol=4e8):
    return {"id": cid, "symbol": sym, "name": cid.title(), "market_cap": mcap, "total_volume": vol, "current_price": 1.5,
            "price_change_percentage_24h_in_currency": ch24, "price_change_percentage_1h_in_currency": ch1,
            "price_change_percentage_7d_in_currency": 20, "market_cap_rank": 40}


def test_cg_markets_moves(monkeypatch):
    data = [coin("solana", "sol", 14.2), coin("tether", "usdt", 12), coin("tiny", "tny", 30, mcap=5e7), coin("calm", "clm", 2, ch1=6.5)]
    monkeypatch.setattr(S, "get_json", lambda *a, **k: data)
    c = ctx({"mem": {"cg_trending_ids": ["solana"]}})
    out = S.c_cg_markets(c)
    ids = {x["id"] for x in out}
    assert "mv:solana:2026-11-23:u1" in ids and "m1:calm:2026-11-23:u1" in ids
    assert not any("tether" in i or "tiny" in i for i in ids)
    sol = next(x for x in out if x["id"].startswith("mv:solana"))
    assert "buscadas" in sol["why"] and sol["m"]["ch24h"] == 14.2 and "solana" in c.share["cg"]


def test_listing_first_run_then_detects(monkeypatch):
    bases = {"coinbase": [{"base_currency": b, "status": "online"} for b in ["BTC", "ETH"] + [f"C{i}" for i in range(30)]]}
    monkeypatch.setattr(S, "get_json", lambda url, **k: bases["coinbase"])
    st = {}
    run = S.listing_collector("coinbase")
    assert run(ctx(st)) == []
    bases["coinbase"].append({"base_currency": "NEW", "status": "online"})
    out = run(ctx(st))
    assert [x["id"] for x in out] == ["ls:coinbase:NEW"] and out[0]["opp"] == 3 and out[0]["cat"] == "lanzamientos"
    assert run(ctx(st)) == []


def test_apewisdom_surge(monkeypatch):
    payload = {"results": [{"ticker": "GME", "name": "GameStop", "mentions": 400, "mentions_24h_ago": 50, "rank": 3, "rank_24h_ago": 40},
                           {"ticker": "AAPL", "name": "Apple", "mentions": 100, "mentions_24h_ago": 90, "rank": 5, "rank_24h_ago": 6}]}
    monkeypatch.setattr(S, "get_json", lambda *a, **k: payload)
    c = ctx()
    out = S.c_apewisdom(c)
    assert {x["id"] for x in out} == {"ape:bolsa:GME:2026-11-23", "ape:cripto:GME:2026-11-23"}
    assert "AAPL" in c.mem("ape_top")


def test_bdns_filters(monkeypatch):
    rows = {"content": [
        {"numeroConvocatoria": "1", "descripcion": "Ayudas para emprendedores y creación de empresas 2027", "fechaRecepcion": "2026-11-22", "nivel1": "AUTONOMICA", "nivel2": "MADRID"},
        {"numeroConvocatoria": "2", "descripcion": "Subvención nominativa a la asociación de empresarios X", "fechaRecepcion": "2026-11-22", "nivel1": "LOCAL"},
        {"numeroConvocatoria": "3", "descripcion": "Ayudas para el pago del IBI", "fechaRecepcion": "2026-11-22", "nivel1": "LOCAL"},
        {"numeroConvocatoria": "4", "descripcion": "Ayudas a la digitalización de pymes", "fechaRecepcion": "2026-10-01", "nivel1": "ESTADO"}]}
    monkeypatch.setattr(S, "get_json", lambda *a, **k: rows)
    out = S.c_bdns(ctx())
    assert [x["id"] for x in out] == ["gr:1"] and out[0]["s"] >= 70 and out[0]["opp"] == 3


def news(id_, title, src="CoinDesk", s=55, cat="cripto"):
    return {"id": id_, "cat": cat, "kind": "news", "src": src, "title": title, "url": f"https://{src}.com/{id_}", "s": s, "opp": 2, "risk": "alto"}


def test_merge_dedupe_cluster_and_seen():
    seen = {}
    items, added = pulse.merge([], [news("n:1", "Binance will list FooCoin FOO token next week")], seen, NOW)
    assert len(added) == 1 and added[0]["t"] == "2026-11-23T15:00:00Z" and added[0]["w"] == added[0]["t"]
    later = NOW + timedelta(minutes=5)
    items, added = pulse.merge(items, [news("n:2", "Binance will list FooCoin (FOO) token next week, exchange says", src="Decrypt")], seen, later)
    assert added == [] and items[0]["n"] == 2 and items[0]["s"] == 61 and {x["n"] for x in items[0]["srcs"]} == {"CoinDesk", "Decrypt"}
    items2, added2 = pulse.merge([], [news("n:1", "x" * 30)], seen, later)
    assert added2 == [] and items2 == []


def test_merge_clusters_cross_language_by_proper_nouns():
    seen = {}
    items, _ = pulse.merge([], [news("n:en", "Linamar to acquire Terex's Genie business for $1.4B", src="Seeking Alpha", cat="bolsa")], seen, NOW)
    items, added = pulse.merge(items, [news("n:es", "Linamar adquirirá el negocio Genie de Terex por 1.400 millones", src="Investing.com", cat="negocio")],
                               seen, NOW + timedelta(minutes=5))
    assert added == [] and items[0]["n"] == 2


def test_merge_clusters_same_event_same_entities():
    seen = {}
    a = dict(news("n:a", "Anthropic raises record $81b in IPO at $1.5t valuation", src="Reuters", cat="lanzamientos"), tags=["ipo"])
    b = dict(news("n:b", "Anthropic clinches biggest IPO ever with $81 billion offering", src="CNBC", cat="lanzamientos"), tags=["ipo"])
    c = dict(news("n:c", "Binance Will Launch Stock Options on Anthropic (ANT)", src="Decrypt", cat="lanzamientos"), tags=["listado"])
    items, added = pulse.merge([], [a, b, c], seen, NOW)
    assert len(added) == 2 and any(x.get("n") == 2 for x in items)


def test_merge_updates_market_item():
    first = {"id": "mv:sol:d:u1", "cat": "cripto", "kind": "move", "src": "CoinGecko", "title": "SOL sube 11%", "es": "SOL sube 11%", "s": 60, "opp": 2,
             "risk": "alto", "m": {"ch24h": 11}}
    items, _ = pulse.merge([], [first], {}, NOW)
    upd = dict(first, es="SOL sube 14%", s=66, m={"ch24h": 14})
    items, added = pulse.merge(items, [upd], {}, NOW + timedelta(minutes=5))
    assert added == [] and items[0]["s"] == 66 and items[0]["m"]["ch24h"] == 14 and items[0]["es"] == "SOL sube 14%" and items[0]["u"]


def test_prune_keeps_by_kind_and_sorts():
    old = (NOW - timedelta(hours=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new = (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = [dict(news("n:a", "a" * 20), t=old, w=old), {"id": "mv:x", "kind": "move", "cat": "cripto", "t": old, "w": old, "s": 70},
             dict(news("n:b", "b" * 20), t=new, w=new), {"id": "ls:x", "kind": "listing", "cat": "lanzamientos", "t": old, "w": old, "s": 80}]
    out = pulse.prune(items, {}, NOW)
    assert [x["id"] for x in out] == ["n:b", "n:a", "ls:x"] or [x["id"] for x in out] == ["n:b", "ls:x", "n:a"]
    assert "mv:x" not in {x["id"] for x in out}


def test_alerts_limits_and_quiet(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "radar-abcdefghijklmnopqrstuv")
    sent = []
    monkeypatch.setattr(notify, "send", lambda title, msg, **kw: sent.append((title, msg)) or True)
    st = {}
    hot = [dict(news(f"n:{i}", f"Big listing number {i} on Binance today"), s=90, es=f"Listado {i}") for i in range(5)]
    assert pulse.alerts(hot, st, {}, NOW) == 1 and "3 oportunidades" in sent[0][0]
    for k in range(2):
        pulse.alerts([dict(hot[0], id=f"x{k}")], st, {}, NOW + timedelta(minutes=5 * (k + 1)))
    assert len(sent) == 3
    assert pulse.alerts([dict(hot[0], id="x9")], st, {}, NOW + timedelta(minutes=20)) == 0
    night = datetime(2026, 11, 24, 1, 0, tzinfo=timezone.utc)
    assert pulse.alerts([dict(hot[0], id="n1", s=90)], st, {}, night) == 0
    assert pulse.alerts([dict(hot[0], id="n2", s=95)], st, {}, night) == 1


def test_triage_applies_ai(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    class R_:
        def __init__(self, data):
            self._d = data

        def json(self):
            return self._d

    def transport(method, url, **kw):
        if url.endswith("/models"):
            return R_({"data": [{"id": "openai/gpt-oss-20b"}]})
        body = {"items": [{"i": 0, "o": 3, "t": "Binance listará FOO la semana que viene", "p": "Los listados suelen subir el precio.",
                           "a": "Vigila FOO; no persigas la subida.", "c": "lanzamientos", "r": "alto"},
                          {"i": 1, "o": 0, "t": "Ruido", "p": "-", "a": "-", "c": "cripto", "r": "medio"}]}
        return R_({"choices": [{"message": {"content": json.dumps(body)}}]})
    a = [news("n:1", "Binance will list FOO next week", s=60), news("n:2", "Celebrity says crypto is cool", s=45)]
    info = pulse.triage(a, {}, {}, NOW, transport=transport)
    assert info["calls"] == 1 and a[0]["es"].startswith("Binance listará") and a[0]["opp"] == 3 and a[0]["s"] == 72 and a[0]["cat"] == "lanzamientos"
    assert a[1]["h"] == 1 and a[1]["s"] == 20


def test_run_end_to_end(tmp_path, monkeypatch):
    def fake(c):
        return [news("n:9", "Coinbase will list BarCoin (BAR) for trading", s=70, cat="lanzamientos")]
    monkeypatch.setattr(S, "registry", lambda cfg: [("Fake", fake, 5)])
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    live, data = tmp_path / "live", tmp_path / "data"
    feed = pulse.run(live, data, {}, now=NOW)
    assert feed["run"]["added"] == 1 and feed["sources"]["Fake"]["ok"] and (live / "feed.json").exists()
    st = json.loads((live / "pulse_state.json").read_text())
    assert "n:9" in st["seen"] and st["last"]["Fake"]
    feed2 = pulse.run(live, data, {}, now=NOW + timedelta(minutes=1))
    assert feed2["run"]["collectors"] == 0 and len(feed2["items"]) == 1
    feed3 = pulse.run(live, data, {}, now=NOW + timedelta(minutes=6))
    assert feed3["run"]["collectors"] == 1 and feed3["run"]["added"] == 0


def test_registry_has_core_sources():
    names = {n for n, _, _ in S.registry({})}
    for n in ("CoinGecko mercado", "Anuncios Binance", "StockTwits", "Reddit (ApeWisdom)", "Ayudas públicas (BDNS)", "CoinDesk", "Altas Coinbase"):
        assert n in names
    assert all(e >= 5 for _, _, e in S.registry({}))


def test_us_session():
    assert S.us_session(datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)) == "open"
    assert S.us_session(datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)) == "ext"
    assert S.us_session(datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)) == "closed"


CNBC_FIX = {"FormattedQuoteResult": {"FormattedQuote": [
    {"symbol": ".SPX", "last": "7,237.17", "change": "+326.78", "change_pct": "+4.73%"},
    {"symbol": ".IXIC", "last": "24,089.558", "change": "+1,471.825", "change_pct": "+6.51%"},
    {"symbol": "US10Y", "last": "4.906%", "change": "-0.114", "change_pct": "-2.28%"},
    {"symbol": "@LCO.1", "last": "89.08", "change": "-0.29", "change_pct": "-0.32%"},
    {"symbol": "@GC.1", "last": "3,622.50", "change": "-28.90", "change_pct": "-0.79%"},
    {"symbol": "@SI.1", "last": "41.825", "change": "-1.35", "change_pct": "-3.13%"}]}}


def test_macro_quotes_and_moves(monkeypatch):
    monkeypatch.setattr(S, "get_json", lambda url, **kw: CNBC_FIX if "cnbc" in url else (_ for _ in ()).throw(S.SourceError("x")))
    c = ctx()
    out = S.c_macro(c)
    q = c.share["macro"]
    assert q["GOLD"]["p"] == 3622.5 and q["SPX"]["p"] == 7237.17 and q["US10Y"]["p"] == 4.906 and q["US10Y"]["chg"] == -0.114
    ids = {x["id"] for x in out}
    assert ids == {"mc:spx:2026-11-23:u2", "mc:ixic:2026-11-23:u3", "mc:silver:2026-11-23:d1", "mc:us10y:2026-11-23:d1"}
    y = next(x for x in out if x["id"].startswith("mc:us10y"))
    assert "11 pb" in y["es"] and "4,91 %" in y["es"]


def test_macro_fallbacks(monkeypatch):
    def fake(url, **kw):
        if "cnbc" in url:
            raise S.SourceError("HTTP 403")
        if "gold-api" in url:
            return {"price": 3600.1 if url.endswith("XAU") else 41.0, "updatedAt": "2026-11-24T10:00:00Z"}
        if "yahoo" in url:
            return {"chart": {"result": [{"meta": {"regularMarketPrice": 89.0, "chartPreviousClose": 88.0}}]}}
        raise S.SourceError("x")
    monkeypatch.setattr(S, "get_json", fake)
    q = S.macro_quotes()
    assert q["GOLD"]["src"] == "gold-api.com" and q["BRENT"]["src"] == "Yahoo" and round(q["BRENT"]["ch"], 2) == 1.14


def test_migration_to_usd(tmp_path, monkeypatch):
    live, data = tmp_path / "live", tmp_path / "data"
    live.mkdir()
    eur = {"id": "mv:sol:2026-11-23:u1", "cat": "cripto", "kind": "move", "src": "CoinGecko", "title": "SOL", "s": 60, "opp": 2, "risk": "alto",
           "m": {"cur": "EUR", "price": 60}, "t": "2026-11-23T14:00:00Z", "w": "2026-11-23T14:00:00Z"}
    keep = dict(news("n:keep", "Una noticia cualquiera de hoy"), t="2026-11-23T14:00:00Z", w="2026-11-23T14:00:00Z")
    (live / "feed.json").write_text(json.dumps({"items": [eur, keep], "ticker": {"BTC": {"p": 1, "cur": "EUR"}}}))
    (live / "pulse_state.json").write_text(json.dumps({"v": 5, "seen": {eur["id"]: "x", "n:keep": "x"}, "mem": {}}))
    monkeypatch.setattr(S, "registry", lambda cfg: [])
    feed = pulse.run(live, data, {}, now=NOW)
    st = json.loads((live / "pulse_state.json").read_text())
    assert [x["id"] for x in feed["items"]] == ["n:keep"] and st["v"] == 6 and eur["id"] not in st["seen"] and "BTC" not in feed["ticker"]


def test_all_collectors_with_fixtures(monkeypatch):
    """Cada colector con datos de ejemplo: no debe lanzar excepciones y debe producir elementos válidos."""
    import time as _t
    now_ms = int(NOW.timestamp() * 1000)
    fixtures = {
        "/quote": {"c": 120.0, "dp": 9.5, "d": 10, "pc": 110},
        "/news": [{"datetime": int(NOW.timestamp()) - 600, "headline": "Acme to acquire Beta Corp in $2 billion deal", "summary": "Deal", "url": "https://n.example/a", "source": "Reuters"}],
        "/calendar/ipo": {"ipoCalendar": [{"date": "2026-11-25", "exchange": "NASDAQ", "name": "Gamma Inc", "numberOfShares": 1e7, "price": "15-17", "status": "expected", "symbol": "GMMA", "totalSharesValue": 6e8}]},
        "/calendar/earnings": {"earningsCalendar": [{"date": "2026-11-23", "epsActual": 1.5, "epsEstimate": 1.2, "hour": "amc", "symbol": "NVDA"},
                                                    {"date": "2026-11-23", "epsActual": None, "epsEstimate": 2.0, "hour": "bmo", "symbol": "AAPL"}]},
        "/stock/insider-transactions": {"data": [{"name": "CEO", "change": 10000, "transactionCode": "P", "transactionPrice": 50, "transactionDate": "2026-11-20"},
                                                 {"name": "CFO", "change": 5000, "transactionCode": "P", "transactionPrice": 50, "transactionDate": "2026-11-19"}]},
        "llama.fi/protocols": [{"slug": "newfi", "name": "NewFi", "symbol": "-", "category": "Lending", "tvl": 2e7, "change_1d": 30, "change_7d": 80, "listedAt": NOW.timestamp() - 5 * 86400},
                               {"slug": "big", "name": "Big", "symbol": "BIG", "category": "Dexs", "tvl": 5e8, "change_1d": 25, "change_7d": 30, "listedAt": NOW.timestamp() - 900 * 86400}],
        "binance.com": {"data": {"catalogs": [{"articles": [{"id": 9, "code": "x1", "title": "Binance Will List Zeta (ZETA) with Seed Tag Applied", "releaseDate": now_ms - 3600000},
                                                             {"id": 8, "code": "x2", "title": "Binance Futures Will Launch USDⓈ-Margined ABCUSDT Perpetual Contract", "releaseDate": now_ms}]}]}},
        "okx.com/api/v5/support": {"data": [{"details": [{"title": "OKX will launch GRVT/USD for spot trading", "url": "https://okx.com/a", "pTime": str(now_ms - 7200000)}]}]},
        "stocktwits": {"symbols": [{"symbol": "HPE", "title": "Hewlett Packard Enterprise"}, {"symbol": "BTC.X", "title": "Bitcoin"}]},
        "bsky.app/xrpc/app.bsky.unspecced": {"topics": [{"displayName": "Nvidia stock jumps", "description": "Shares surge after news", "link": "/x"}]},
        "searchPosts": {"posts": [{"uri": "at://x/app.bsky.feed.post/abc", "likeCount": 120, "record": {"text": "Big airdrop for early users of protocol X on Solana, claim now eligible wallets"}, "author": {"handle": "h.bsky.social"}}]},
        "mastodon.social": [{"title": "Bitcoin rallies as markets cheer", "description": "Crypto markets up", "url": "https://m.example/b", "provider_name": "Example"}],
        "hn.algolia.com/api/v1/search?": {"hits": [{"objectID": "1", "title": "Big AI model release", "points": 600, "num_comments": 200, "url": "https://x.example"}]},
        "search_by_date": {"hits": [{"objectID": "2", "title": "Show HN: My tool", "points": 120, "num_comments": 30, "url": "https://t.example"}]},
        "api.github.com": {"items": [{"full_name": "a/b", "stargazers_count": 2500, "created_at": "2026-11-20T00:00:00Z", "html_url": "https://github.com/a/b", "description": "x"}]},
        "huggingface.co": [{"id": "org/model", "likes": 500, "downloads": 1000, "trendingScore": 300}],
        "alternative.me": {"data": [{"value": "12", "value_classification": "Extreme Fear"}]},
        "massive.com": {"results": [{"T": "NVDA", "c": 130, "v": 5e7}, {"T": "AAPL", "c": 100, "v": 6e7}]},
        "apewisdom.io": {"results": [{"ticker": "GME", "name": "GameStop", "mentions": 400, "mentions_24h_ago": 50, "rank": 3, "rank_24h_ago": 40}]},
        "quote.cnbc.com": CNBC_FIX,
    }

    def fake_get_json(url, **kw):
        params = kw.get("params") or {}
        full = url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        if "cnbc.com" in url:
            return CNBC_FIX
        if "massive.com" in url:
            day = url.rsplit("/", 1)[-1]
            base = {"NVDA": 100, "AAPL": 100}
            mult = 1.0 if day.endswith("19") or day.endswith("18") else 1.2
            return {"results": [{"T": t, "c": base[t] * mult, "v": 5e7} for t in base]}
        for k, v in fixtures.items():
            if k in full:
                return v
        raise S.SourceError("sin fixture: " + full)
    monkeypatch.setattr(S, "get_json", fake_get_json)
    monkeypatch.setenv("FINNHUB_API_KEY", "x")
    monkeypatch.setenv("MASSIVE_API_KEY", "x")
    fund = {"NVDA": {"name": "Nvidia", "m": {"mcap": 3_000_000}}, "AAPL": {"name": "Apple", "m": {"mcap": 3_500_000}}, "ACME": {"name": "Acme", "m": {"mcap": 20_000}}}
    open_time = datetime(2026, 11, 23, 16, 0, tzinfo=timezone.utc)  # NY 11:00, lunes
    c = S.Ctx(open_time, {}, {"profile": {"region": "es"}}, fund=fund, watch=["NVDA", "ACME"])
    results = {}
    for name, fn, _ in S.registry({}):
        if name.startswith("Altas") or name in ("CoinGecko mercado", "CoinGecko tendencias", "Google News", "Ayudas públicas (BDNS)") or fn.__name__.startswith("rss_"):
            continue
        out = fn(c)
        assert isinstance(out, list), name
        for it in out:
            assert it["id"] and it["cat"] in R.CATS and it["kind"] and isinstance(it["s"], int) and 0 <= it["s"] <= 100, (name, it)
        results[name] = out
    kinds = {name: {x["kind"] for x in out} for name, out in results.items()}
    assert "ipo" in kinds["Calendario IPO y resultados"] and "earnings" in kinds["Calendario IPO y resultados"]
    assert any(x["id"].startswith("sm:NVDA") for x in results["Bolsa EE. UU. (cotizaciones)"])
    assert results["Compras de directivos"] and results["Compras de directivos"][0]["kind"] == "insider"
    assert {x["id"] for x in results["DefiLlama"]} == {"dn:newfi", "df:big:2026-11-23"}
    ann = results["Anuncios Binance"]
    assert any(x["id"] == "an:binance:ZETA" and x["kind"] == "listing" for x in ann) and any(x["kind"] == "context" for x in ann)
    assert results["Anuncios OKX"][0]["sym"] == "GRVT"
    assert results["Cierre EE. UU. (Massive)"] and all(x["sym"] in fund for x in results["Cierre EE. UU. (Massive)"])
    assert results["Noticias Finnhub"] and results["Noticias Finnhub"][0]["via"] == "Finnhub"
    assert results["Miedo y codicia"][0]["id"].startswith("fg:")
    assert c.share["macro"]["BRENT"]["p"] == 89.08
