"""Pruebas de la selección estricta y los manuales (IA y red simuladas)."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from radar import net, notify, selection  # noqa: E402

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
NOW = datetime.now(timezone.utc)


class R:
    def __init__(self, data):
        self._d = data
        self.headers = {"Content-Type": "application/json"}
        self.status_code = 200

    def json(self):
        return self._d


def manual(veredicto="confirmada", existe=True):
    return {"segundaOpinion": {"veredicto": veredicto, "motivo": "La web confirma los datos.", "contradicciones": []},
            "viaDeBeneficio": {"existe": existe, "explicacion": "Recompensa por tareas en la beta."},
            "resumen": "Programa de recompensas.", "cuantoPoner": "0 €", "antesDeEmpezar": ["Comprobar el dominio"],
            "pasos": [{"titulo": "Registrarse", "detalle": "En la web oficial", "tiempo": "10 min"}],
            "planDeSalida": "Cobrar al terminar.", "senalesDeAlarma": ["Piden pagos"], "erroresTipicos": ["Usar enlaces no oficiales"],
            "fiscalidad": "Declarar en el IRPF; consulta a un asesor.", "tiempoNecesario": "2 h"}


class Fake:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def __call__(self, method, url, **kw):
        self.calls.append(url)
        if url.endswith("/models"):
            return R({"data": [{"id": m} for m in CFG["models"]["groq_preference"]]})
        if "chat/completions" in url:
            return R({"choices": [{"message": {"content": json.dumps(self.reply)}}]})
        raise AssertionError(url)


def opp(i, score=72, **kw):
    o = {"id": f"o{i}", "name": f"Oportunidad {i}", "category": "lanzamientos", "score": score, "risk": "medio",
         "spainAvailability": "si", "costs": {"minEntry": 0}, "officialUrl": f"https://oficial{i}.example",
         "sources": [{"title": "a", "url": f"https://oficial{i}.example/x"}, {"title": "b", "url": "https://news.example/y"}],
         "flags": [{"code": "sin_verificacion_independiente", "severity": "alta"}],
         "aiModels": {"analyst": "groq:openai/gpt-oss-120b"}, "verification": {"verdict": "sin verificar"},
         "lastSeenAt": NOW.isoformat()}
    o.update(kw)
    return o


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "q")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    sent = []
    monkeypatch.setattr(notify, "send", lambda *a, **k: sent.append(a) or True)
    monkeypatch.setattr(net, "page_text", lambda url, n=6000: "TÍTULO: Web oficial")
    return tmp_path, sent


def write(d, opps):
    (d / "opps.json").write_text(json.dumps(opps), encoding="utf-8")


def test_selects_only_when_all_criteria_pass(data):
    d, sent = data
    write(d, [opp(1, 72), opp(2, 72, spainAvailability="no"), opp(3, 40), opp(4, 90, risk="muy alto")])
    fake = Fake(manual())
    out = selection.run(d, CFG, transport=fake)
    assert [r["id"] for r in out["selected"]] == ["o1"]
    assert out["selected"][0]["adjustedScore"] == 77  # +5 al confirmar la verificación
    assert "o1" in out["manuals"] and out["manuals"]["o1"]["independiente"]
    assert any("llama" in c or "qwen" in c or "chat" in c for c in fake.calls)
    assert len(sent) == 1 and "Seleccionada" in sent[0][0]
    saved = json.loads((d / "selected.json").read_text(encoding="utf-8"))
    assert saved["selected"][0]["id"] == "o1"


def test_doubtful_second_opinion_blocks(data):
    d, _ = data
    write(d, [opp(1, 80)])
    out = selection.run(d, CFG, transport=Fake(manual(veredicto="dudosa")))
    assert out["selected"] == []
    assert "Verificada por un segundo modelo de IA independiente" in out["nearMisses"][0]["failed"]


def test_no_money_route_blocks(data):
    d, _ = data
    write(d, [opp(1, 85)])
    out = selection.run(d, CFG, transport=Fake(manual(existe=False)))
    assert out["selected"] == []
    assert "Vía clara y legal para ganar dinero" in out["nearMisses"][0]["failed"]


def test_cached_manual_not_regenerated_and_alert_once(data):
    d, sent = data
    write(d, [opp(1, 72)])
    selection.run(d, CFG, transport=Fake(manual()))
    fake2 = Fake(manual())
    out = selection.run(d, CFG, transport=fake2)
    assert fake2.calls == []
    assert [r["id"] for r in out["selected"]] == ["o1"]
    assert len(sent) == 1


def test_discarded_and_expired_excluded(data):
    d, _ = data
    past = (NOW - timedelta(days=1)).isoformat()
    write(d, [opp(1, 90, deadline=past), opp(2, 90)])
    (d / "actions.json").write_text(json.dumps({"o2": {"action": "descartada"}}), encoding="utf-8")
    out = selection.run(d, CFG, transport=Fake(manual()))
    assert out["selected"] == []


def test_ai_budget_per_run(data):
    d, _ = data
    write(d, [opp(i, 75) for i in range(12)])
    fake = Fake(manual())
    out = selection.run(d, CFG, transport=fake)
    assert out["ai"]["used"] == selection.MAX_AI_PER_RUN
    assert len(out["selected"]) == selection.MAX_SELECTED


def test_gemini_search_429_falls_back_without_search(monkeypatch):
    from radar import llm
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    seen = []

    def tr(method, url, **kw):
        if url.endswith("pageSize=200"):
            return R({"models": [{"name": "models/gemini-3.1-flash-lite", "supportedGenerationMethods": ["generateContent"]}]})
        body = kw.get("json") or {}
        seen.append("tools" in body)
        if "tools" in body:
            raise net.FetchError("HTTP 429")
        return R({"candidates": [{"content": {"parts": [{"text": '{"verdict": "dudosa"}'}]}}]})

    r = llm.Router(CFG, transport=tr)
    res = r.ask_role("verifier", "s", "p", search=True)
    assert res["data"]["verdict"] == "dudosa" and r.search_blocked
    assert r.ask_role("searcher", "s", "p", search=True, require_search=True) is None
    assert seen == [True, False]  # el buscador ya no gasta llamadas con la búsqueda bloqueada
