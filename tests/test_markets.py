"""Pruebas del radar de mercados (sin red)."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from radar import markets, net, notify, search  # noqa: E402


def series_cross():
    """240 sesiones: sube, luego cae por debajo de la media de 50 y la recupera con volumen."""
    c = [100 + i * 0.2 for i in range(180)] + [136 - i * 0.6 for i in range(57)] + [104, 112, 118]
    v = [1000] * 237 + [2500, 2600, 2700]
    return c, v


def test_indicators_and_trigger():
    c, v = series_cross()
    t = markets.technicals(c, None, None, v)
    assert t["trigger"] and t["trigger"]["type"] == "media50"
    assert t["stop"] < c[-1] and t["riskPct"] > 0
    assert 0 <= t["rsi"] <= 100
    flat = [100.0] * 240
    assert markets.detect_trigger(flat) is None


def test_fscore_lite_and_stage_a():
    good = {"mcap": 3000, "pe": 12, "pb": 1.5, "pfcf": 10, "evFcf": 11, "roi": 15, "roa": 8, "gm": 40, "om": 15, "nm": 10,
            "cr": 2, "de": 0.5, "cov": 10, "revG": 5, "epsG": 8, "roaY": 8, "roaP": 7, "currentRatioY": 2, "currentRatioP": 1.8,
            "grossMarginY": 40, "grossMarginP": 39, "totalDebtToEquityY": 0.5, "totalDebtToEquityP": 0.6}
    n, det = markets.fscore_lite(good)
    assert n == 9 and len(det) == 9
    bad = dict(good, nm=-5, pfcf=-3, pe=None, revG=-30, epsG=-10)
    debt = dict(good, de=4.0)
    cache = {"GOOD": {"m": good, "name": "Good"}, "BAD": {"m": bad, "name": "Bad"}, "DEBT": {"m": debt, "name": "Debt"}}
    prices = {k: {"c": 80.0, "v": 1e6} for k in cache}
    ok, med = markets.score_stocks(cache, prices)
    assert [r["ticker"] for r in ok] == ["GOOD"] and med["universe"] == 3 and med["pe"] == 12


def test_paper_portfolio_open_and_stop():
    item = {"symbol": "AAA", "name": "Aaa", "price": 100.0, "score": 80, "fallingKnife": False,
            "trigger": {"type": "media50", "text": "Recupera su media"}, "tech": {"stop": 90.0}}
    st = {"items": [item], "prices": {"AAA": 100.0, "SPY": 500.0}, "regime": {"riskOn": True}}
    paper = {}
    new = markets.update_paper(paper, st, {"items": [], "prices": {}}, "2026-11-20")
    assert len(new) == 1 and paper["summary"]["open"] == 1
    assert markets.update_paper(paper, st, {"items": [], "prices": {}}, "2026-11-21") == []  # no repite
    st2 = {"items": [], "prices": {"AAA": 89.0, "SPY": 505.0}}
    markets.update_paper(paper, st2, {"items": [], "prices": {}}, "2026-11-22")
    p = paper["positions"][0]
    assert p["status"] == "cerrada" and p["exitReason"] == "stop" and p["returnPct"] == -11.0 and p["benchPct"] == 1.0


def test_run_writes_files_notifies_and_skips(tmp_path, monkeypatch):
    item = {"symbol": "AAA", "name": "Aaa", "price": 100.0, "score": 80, "fallingKnife": False,
            "trigger": {"type": "media50", "text": "Recupera su media"}, "tech": {"stop": 90.0}}
    monkeypatch.setattr(markets, "stocks", lambda d: {"enabled": True, "items": [item], "prices": {"AAA": 100.0}, "regime": {"riskOn": True}})
    monkeypatch.setattr(markets, "crypto", lambda: {"enabled": True, "items": [], "prices": {}, "btc": 1.0})
    monkeypatch.setattr(markets, "ape", lambda kind: {})
    monkeypatch.setattr(markets, "news", lambda q: [{"title": "t", "url": "https://x.example"}])
    sent = []
    monkeypatch.setattr(notify, "send", lambda *a, **k: sent.append(a) or True)
    out = markets.run(tmp_path)
    assert out["newSignals"] and len(sent) == 1 and "AAA" in sent[0][0]
    saved = json.loads((tmp_path / "markets.json").read_text(encoding="utf-8"))
    assert saved["stocks"]["items"][0]["news"][0]["url"] == "https://x.example" and "prices" not in saved["stocks"]
    assert markets.run(tmp_path).get("skipped")


def test_tavily_parsing_and_cap(monkeypatch):
    class R:
        def json(self):
            return {"results": [{"title": "A", "url": "https://a.example", "content": "x"}, {"title": "bad", "url": "ftp://x"}]}
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(net, "request", lambda *a, **k: R())
    search.USED["calls"] = 0
    assert [x["url"] for x in search.tavily("q")] == ["https://a.example"]
    search.USED["calls"] = search.MAX_CALLS_PER_RUN
    assert search.tavily("q") == []
    search.USED["calls"] = 0
