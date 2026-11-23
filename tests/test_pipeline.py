"""Prueba de extremo a extremo con red y modelos simulados (sin claves reales ni Internet)."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from radar import llm, net, notify, pipeline  # noqa: E402

NOW_MS = time.time() * 1000


class R:
    def __init__(self, data=None, text=None, status=200, ctype="application/json"):
        self._d, self.text, self.status_code = data, text if text is not None else json.dumps(data), status
        self.headers = {"Content-Type": ctype}
        self.url = ""

    def json(self):
        return self._d if self._d is not None else json.loads(self.text)


SUBS = {k: {"v": 9, "why": "dato de prueba", "evidence": True} for k in pipeline.CRIT_KEYS}
FICHA = {"name": "Proyecto Beta IA", "category": "ia_tecnologia", "subcategory": "Acceso anticipado", "kind": "activa",
         "description": "Plataforma de prueba.", "officialUrl": "https://beta-ia.example", "participateUrl": "https://beta-ia.example/join",
         "country": "España", "spainAvailability": "si", "costs": {"minEntry": 0, "extra": 0, "recommended": 0, "max": 0},
         "canLoseAll": False, "liquidity": "no aplica", "horizon": "1-3 meses", "subscores": SUBS, "redFlags": [],
         "whyInteresting": ["Gratis"], "howToParticipate": ["Registrarse"], "lossCauses": ["Tiempo"], "signals": {"members": 1200}}
CALLS = {"gemini": 0, "groq": 0, "ntfy": []}


def fake_request(method, url, **kw):
    if "frankfurter" in url:
        return R({"rates": {"EUR": 0.91}})
    if "token-profiles" in url or "token-boosts" in url:
        return R([{"chainId": "base", "tokenAddress": "0xGOOD"}, {"chainId": "base", "tokenAddress": "0xHONEY"}])
    if "latest/dex/tokens" in url:
        mk = lambda addr, sells, liq: {"chainId": "base", "baseToken": {"address": addr, "name": addr, "symbol": addr[2:6]},
                                        "priceUsd": "0.01", "liquidity": {"usd": liq}, "volume": {"h24": 90000}, "fdv": 2_000_000,
                                        "pairCreatedAt": NOW_MS - 5 * 86400e3, "txns": {"h24": {"buys": 300, "sells": sells}},
                                        "url": f"https://dexscreener.com/base/{addr}", "info": {"websites": [{"url": "https://good.example"}]}}
        return R({"pairs": [mk("0xGOOD", 250, 400000), mk("0xHONEY", 0, 400000)]})
    if "geckoterminal" in url:
        return R({"data": []})
    if "coingecko" in url:
        return R({"coins": []})
    if "hn.algolia" in url:
        return R({"hits": [{"title": "Show HN: Herramienta X", "url": "https://x.example", "points": 120, "num_comments": 40, "objectID": "1"}]})
    if "api.github.com" in url:
        return R({"items": []})
    if url.endswith("/feed/") or "rss" in url or url.endswith("/feed"):
        return R(text="<rss><channel><item><title>Ronda seed</title><link>https://n.example/a</link><description>x</description></item></channel></rss>", ctype="application/xml")
    if "gopluslabs" in url:
        return R({"result": {"0xgood": {"is_honeypot": "0", "holders": [{"percent": "0.05"}] * 10, "holder_count": "5400"}}})
    if "honeypot.is" in url:
        return R({"honeypotResult": {"isHoneypot": False}})
    if "generativelanguage" in url and method == "GET":
        return R({"models": [{"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]}]})
    if "generativelanguage" in url:
        CALLS["gemini"] += 1
        prompt = kw["json"]["contents"][0]["parts"][0]["text"]
        if "Busca:" in prompt:
            payload = {"candidates": [{"name": "Proyecto Beta IA", "officialUrl": "https://beta-ia.example", "summary": "s", "whyNow": "w",
                                       "sourceUrls": ["https://news.example/beta"]}]}
        else:
            subs = {k: {"v": 9, "why": "verificado", "evidence": True} for k in pipeline.CRIT_KEYS}
            subs["equipo"] = {"v": 2, "why": "equipo no verificable", "evidence": True}
            payload = {"verdict": "confirmada", "subscores": subs, "redFlags": [],
                       "regulatory": {"checked": True, "status": "no_aplica", "notes": "sin advertencias CNMV", "sources": ["https://www.cnmv.es"]},
                       "sources": [{"title": "CNMV", "url": "https://www.cnmv.es"}]}
        return R({"candidates": [{"content": {"parts": [{"text": "```json\n" + json.dumps(payload) + "\n```"}]},
                                  "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://src.example", "title": "src"}}]}}]})
    if "groq.com" in url and method == "GET":
        return R({"data": [{"id": "llama-3.3-70b-versatile"}]})
    if "groq.com" in url:
        CALLS["groq"] += 1
        body = kw["json"]["messages"][1]["content"]
        f = dict(FICHA)
        if "0xGOOD" in body or "good.example" in body:
            f = dict(FICHA, name="GOOD token", category="cripto", kind="pasiva", canLoseAll=True, officialUrl="https://good.example",
                     costs={"minEntry": 10, "extra": 2, "recommended": 40, "max": 150}, liquidity="media")
        elif "Herramienta X" in body:
            f = dict(FICHA, name="Herramienta X", officialUrl="https://x.example")
        elif "Ronda seed" in body:
            f = dict(FICHA, name="Ronda seed", officialUrl="https://n.example/a", category="startups")
        return R({"choices": [{"message": {"content": json.dumps(f)}}]})
    if "ntfy" in url:
        CALLS["ntfy"].append(kw["json"])
        return R({"id": "x"})
    raise AssertionError("URL no simulada: " + url)


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(net, "request", fake_request)
    monkeypatch.setattr(net, "page_text", lambda url, n=6000: "TÍTULO: Web oficial\nTexto de ejemplo")
    monkeypatch.setattr(net, "allowed_by_robots", lambda url: True)
    monkeypatch.setattr(net, "MIN_INTERVAL", 0)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("GROQ_API_KEY", "q")
    monkeypatch.setenv("NTFY_TOPIC", "radar-test")
    monkeypatch.setenv("APP_URL", "https://user.github.io/radar/")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    CALLS.update({"gemini": 0, "groq": 0, "ntfy": []})
    feed = {"items": [{"id": "n:good", "cat": "lanzamientos", "also": ["cripto"], "kind": "news", "src": "CoinDesk", "s": 80, "opp": 3,
                       "title": "GOOD protocol opens airdrop points program", "url": "https://good.example/airdrop"},
                      {"id": "n:low", "cat": "cripto", "kind": "news", "src": "CoinDesk", "s": 40, "opp": 1, "title": "Ruido", "url": "https://x.example/r"}]}
    (tmp_path / "pulse_feed.json").write_text(json.dumps(feed))
    monkeypatch.setenv("PULSE_FEED", str(tmp_path / "pulse_feed.json"))
    yield tmp_path


def test_full_scan(env):
    log = pipeline.run("scan", env)
    opps = json.loads((env / "opps.json").read_text())
    names = {o["name"] for o in opps}
    assert "Proyecto Beta IA" in names and "GOOD token" in names
    assert not any("HONEY" in n for n in names), "el token sin ventas debe filtrarse antes de gastar IA"
    beta = next(o for o in opps if o["name"] == "Proyecto Beta IA")
    # consenso: 8 vs 2 en equipo → se toma el bajo y se pierde la evidencia
    eq = beta["subscores"]["equipo"]
    assert eq["v"] == 2 and eq["evidence"] is False and "Discrepancia" in eq["why"]
    assert beta["aiModels"]["analyst"].startswith("groq:") and beta["aiModels"]["verifier"].startswith("gemini:")
    assert beta["verification"]["verdict"] == "confirmada" and beta["regulatory"]["status"] == "no_aplica"
    tok = next(o for o in opps if o["name"] == "GOOD token")
    assert tok["discoveredVia"].startswith("Pulso") and tok["scenarios"]["stakeEur"] == 40
    st = json.loads((env / "state.json").read_text())
    assert "n:good" in st["pulseDone"] and "n:low" not in st["pulseDone"]
    assert log["status"] in ("ok", "parcial") and log["candidates"] >= 3
    status = json.loads((env / "status.json").read_text())
    assert status["sources"]["busqueda_ia"]["ok"] and status["ai"]["calls"]["groq"] >= 3


def test_dedupe_and_no_reanalysis(env):
    pipeline.run("scan", env)
    g1 = CALLS["groq"]
    pipeline.run("scan", env)
    assert CALLS["groq"] == g1, "lo analizado hace menos de 20 h no vuelve a gastar IA"
    opps = json.loads((env / "opps.json").read_text())
    assert len({o["id"] for o in opps}) == len(opps)


def test_alert_sent_and_not_repeated(env):
    pipeline.run("scan", env)
    first = [n for n in CALLS["ntfy"] if "oportunidad" in n["title"].lower() or "URGENTE" in n["title"]]
    assert first, "debe avisar de la oportunidad por encima del umbral"
    assert first[0]["click"].startswith("https://user.github.io/radar/#")
    assert "NOMBRE:" in first[0]["message"] and "QUÉ PODRÍA HACERME PERDER EL DINERO:" in first[0]["message"]
    CALLS["ntfy"].clear()
    # forzar re-análisis: marcar como vista hace 2 días
    p = env / "opps.json"
    data = json.loads(p.read_text())
    for o in data:
        o["lastSeenAt"] = "2020-01-01T00:00:00Z"
    p.write_text(json.dumps(data))
    pipeline.run("scan", env)
    again = [n for n in CALLS["ntfy"] if "Nueva oportunidad" in n["title"]]
    assert not again, "no debe repetir la alerta de la misma oportunidad"


def test_discarded_by_user_is_skipped(env):
    pipeline.run("scan", env)
    opps = json.loads((env / "opps.json").read_text())
    beta = next(o for o in opps if o["name"] == "Proyecto Beta IA")
    (env / "actions.json").write_text(json.dumps({beta["id"]: {"action": "descartada"}}))
    for o in opps:
        o["lastSeenAt"] = "2020-01-01T00:00:00Z"
    (env / "opps.json").write_text(json.dumps(opps))
    g1 = CALLS["groq"]
    pipeline.run("scan", env)
    assert CALLS["groq"] - g1 <= 3  # Beta no se re-analiza


def test_without_ai_keys_still_collects(env, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.delenv("GROQ_API_KEY")
    log = pipeline.run("scan", env)
    assert log["status"] != "error"
    assert "Sin modelos de IA" in log["notes"]


def test_budget_cap_on_llm_calls(env, monkeypatch):
    cfg = json.loads(Path("config.json").read_text())
    r = llm.Router({**cfg, "limits": {"max_llm_calls": {"groq": 1}}}, transport=fake_request)
    assert r.ask("groq", "s", "p")["data"]
    with pytest.raises(llm.BudgetExceeded):
        r.ask("groq", "s", "p")


def test_extract_json_variants():
    assert llm.extract_json('texto {"a": {"b": "}"}} fin') == {"a": {"b": "}"}}
    assert llm.extract_json("```json\n[1,2]\n```") == [1, 2]
    with pytest.raises(llm.LLMError):
        llm.extract_json("nada")


def test_digest(env):
    pipeline.run("scan", env)
    pipeline.run("digest", env)
    d = json.loads((env / "digests.json").read_text())
    assert d[0]["type"] == "diaria" and "Resumen diario" in d[0]["text"]
    assert any("Resumen diario" in n["title"] for n in CALLS["ntfy"])


def test_budget_above_150_requires_authorization(env):
    (env / "profile.json").write_text(json.dumps({"budget": 1000}))
    pipeline.run("scan", env)
    opps = json.loads((env / "opps.json").read_text())
    assert all((o.get("scenarios") or {}).get("stakeEur", 0) <= 150 for o in opps)
