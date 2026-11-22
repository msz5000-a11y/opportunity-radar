"""Pruebas de la pestaña Ideas (IA y red simuladas)."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from radar import ideas, net, notify  # noqa: E402
from radar.llm import Router  # noqa: E402

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DEEP = {"name": "Shiftly", "type": "saas", "originCountry": "Brasil", "summary": "Turnos para restaurantes.",
        "traction": ["Levantó 5 millones de dólares", "Tiene 2.000 clientes", "Dato inventado"],
        "whyItWorked": ["dolor claro"], "markets": {"es": {"fit": 8}, "eg": {"fit": 6}, "gcc": {"fit": 7}},
        "mvp": {"costEur": [1500, 6000], "weeks": 8}, "monetization": "suscripción", "risks": ["competencia"],
        "firstSteps": ["entrevistar 10 restaurantes"], "officialUrl": "https://shiftly.example"}


def fake_ask_role(self, role, system, prompt, **kw):
    if "Elige como máximo" in prompt:
        return {"data": {"picks": [{"i": 0, "why": "modelo simple"}, {"i": 9, "why": "fuera de rango"}]}, "provider": "groq", "model": "m"}
    if "Analiza la idea" in prompt:
        return {"data": dict(DEEP), "provider": "groq", "model": "m"}
    if "aparecen realmente" in prompt:
        return {"data": {"supported": [0, 1]}, "provider": "gemini", "model": "g"}
    return None


def test_ideas_run(tmp_path, monkeypatch):
    monkeypatch.setattr(ideas, "gather", lambda cfg: ([{"title": "Shiftly raises $5M", "url": "https://news.example/a", "summary": "s", "source": "TC"}], {}))
    monkeypatch.setattr(net, "page_text", lambda url, n=6000: "Shiftly raised $5M and has 2,000 customers. Visit https://shiftly.example " + "x" * 400)
    monkeypatch.setattr(Router, "ask_role", fake_ask_role)
    sent = []
    monkeypatch.setattr(notify, "send", lambda *a, **k: sent.append(a) or True)
    out = ideas.run(tmp_path, CFG)
    it = out["items"][0]
    assert it["name"] == "Shiftly" and it["verified"] and it["droppedFacts"] == 1 and len(it["traction"]) == 2
    assert it["links"][0]["url"] == "https://news.example/a" and any(l["title"] == "Web oficial" for l in it["links"])
    assert it["score"] >= 75 and len(sent) == 1
    assert ideas.run(tmp_path, CFG).get("skipped")
    out2 = ideas.run(tmp_path, CFG, force=True)  # misma URL ya vista: no se repite
    assert out2["newCount"] == 0 and len(out2["items"]) == 1
