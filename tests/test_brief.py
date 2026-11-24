"""Pruebas del informe «Para ti» (radar/brief.py) y de la señal de ruptura del radar de mercados."""
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar import brief as B
from radar import markets as M

NOW = datetime(2026, 11, 24, 7, 0, tzinfo=timezone.utc)  # 08:00 en Madrid

SX = """<div class="syndicate syndicate-opened"> <a href="https://startupxplore.com/es/inversores/invertir-startups/acme" class="link-to-syndicate">
<img src="x.png" class="logo" alt="ACME"/> <span class="status">Abierta</span> <h3> Acme Robots </h3>
<span class="category">robotics</span> <div class="label-type-investment type-1 type-EQUITY"></div>
<div class="data"><span>Invertidos</span> <p class="green"> 120.500 &euro; </p></div>
<div class="data"><span>Obj. Min.</span> <p>100.000 &euro;</p></div><div class="data"><span>Obj. Max.</span> <p> 300.000 &euro; </p></div>
<li><span class="number">31</span> Inversores</li><li><span class="number">40,2%</span> completado</li>
<b class="countdown-text" data-countdown="2026/12/20">Cargando...</b></a></div>
<div class="syndicate syndicate-opened"> <a href="https://startupxplore.com/es/inversores/invertir-startups/acme" class="link-to-syndicate"></a></div>"""
SX_DEAL = "<p>Inversión mínima: <b>500 €</b> por participación</p>"
CC = """<div><span>12</span> <span>días restantes</span><span>Objetivo</span><span>€1.500.000</span><span>Invertido</span><span>64.5%</span>
<h3>Bio Cosa</h3><p>Terapia nueva para una enfermedad rara que hoy no tiene tratamiento eficaz.</p><a href="https://capitalcell.com/campaign/bio-cosa/">Ver detalles de la inversión</a></div>"""
CC_DEAL = "<li>Valoración Premoney</li><li>9.000.000</li><li>&euro;</li><li>Sector</li><li>Biotecnología</li><li>Equity ofrecido </li><li>14.3%</li><li>Inversión mínima</li><li>1.000</li><li>&euro;</li>"
DZ = """<h2>Oportunidades de inversión abiertas</h2><p>Incentivo fiscal</p><h3>Mygocu</h3><p>El Shopify de los organizadores de viajes</p>
<p>350.000 €</p><p>431.500 € invertidos (123%)</p><p>Quedan 5 días para el cierre</p><a href="/oportunidades-de-inversion/my-gocu/">Ver detalle</a>
<p>Financiada</p><h3>Vivla</h3><p>Co-propiedad</p><p>2.600.000 €</p><p>Importe total de la ronda</p><a href="/oportunidades-de-inversion/vivla-closed/">Ver detalle</a>
<h2>Otras empresas en las que hemos invertido</h2>"""
DZ_DEAL = "<p>Tipo de inversión: Préstamo convertible</p><p>Ticket mínimo</p><p>5.000€</p><p>CAP</p><p>7.500.000</p>"
PAGES = {"https://startupxplore.com/es/inversores/invertir-startups": SX,
         "https://startupxplore.com/es/inversores/invertir-startups/acme": SX_DEAL,
         "https://capitalcell.net/": CC, "https://capitalcell.com/campaign/bio-cosa/": CC_DEAL,
         "https://dozeninvestments.com/oportunidades-de-inversion/": DZ,
         "https://dozeninvestments.com/oportunidades-de-inversion/my-gocu/": DZ_DEAL}


def test_round_parsers(monkeypatch):
    monkeypatch.setattr(B, "_get", lambda url, **kw: PAGES[url])
    sx = B.startupxplore()
    assert len(sx) == 1 and sx[0]["empresa"] == "ACME" and sx[0]["invertido_eur"] == 120500 and sx[0]["completado_pct"] == 40.2
    assert sx[0]["cierre"] == "2026-12-20" and sx[0]["ticket_min_eur"] == 500 and sx[0]["tipo"] == "acciones"
    cc = B.capitalcell()
    assert cc[0]["empresa"] == "Bio Cosa" and cc[0]["objetivo_eur"] == 1500000 and cc[0]["ticket_min_eur"] == 1000
    assert cc[0]["valoracion_premoney_eur"] == 9000000 and cc[0]["participacion_ofrecida"] == "14.3%" and cc[0]["sector"] == "Biotecnología"
    dz = B.dozen()
    assert [d["empresa"] for d in dz] == ["Mygocu"] and dz[0]["ticket_min_eur"] == 5000 and dz[0]["tipo"] == "Préstamo convertible"
    assert dz[0]["cap_valoracion_eur"] == 7500000 and dz[0]["url"].endswith("/my-gocu/")
    allr = B.rounds()
    assert [r["id"] for r in allr] == ["st1", "st2", "st3"]


def test_num_parsing():
    assert B._num("586.552 €") == 586552 and B._num("€3.250.000") == 3250000 and B._num("92.8%") == 92.8
    assert B._num("1.000,50") == 1000.5 and B._num("40,2") == 40.2 and B._num(None) is None


TRUST = ('self.__next_f.push([1,"x:{\\"name\\":\\"Leadly\\",\\"icon\\":\\"i.png\\",\\"description\\":\\"Leads for dentists\\",\\"currentMrr\\":9000,'
         '\\"currentLast30DaysRevenue\\":9500,\\"slug\\":\\"leadly\\",\\"userCategory\\":\\"Marketing\\",\\"growth30d\\":40.5},'
         '{\\"name\\":\\"Gumroad\\",\\"icon\\":\\"g.png\\",\\"description\\":\\"Sell\\",\\"currentLast30DaysRevenue\\":7143937,\\"slug\\":\\"gumroad\\"}"])')


def test_trustmrr_keeps_small_real_businesses(monkeypatch):
    monkeypatch.setattr(B, "_get", lambda url, **kw: TRUST)
    t = B.trustmrr()
    assert [x["nombre"] for x in t] == ["Leadly"]
    assert t[0]["ingresos_30d_usd"] == 9500 and t[0]["url"] == "https://trustmrr.com/startup/leadly" and t[0]["categoria"] == "Marketing"


def _detail(num, tipo="Concurrencia competitiva - canónica", benef="PYME Y PERSONAS FÍSICAS QUE DESARROLLAN ACTIVIDAD ECONÓMICA",
            nivel="ESTADO", fin="2026-12-31", region="ES - ESPAÑA"):
    return {"descripcion": f"Ayuda {num}", "tipoConvocatoria": tipo, "tiposBeneficiarios": [{"descripcion": benef}],
            "organo": {"nivel1": nivel, "nivel2": "MINISTERIO", "nivel3": "X"}, "regiones": [{"descripcion": region}],
            "fechaInicioSolicitud": "2026-11-01", "fechaFinSolicitud": fin, "abierto": True, "presupuestoTotal": 1000000,
            "descripcionFinalidad": "Industria", "instrumentos": [{"descripcion": "SUBVENCIÓN"}]}


def test_grants_only_open_competitive_for_people_or_smes(monkeypatch):
    details = {"1": _detail("1"), "2": _detail("2", tipo="Concesión directa - instrumental"),
               "3": _detail("3", benef="PERSONAS JURÍDICAS QUE NO DESARROLLAN ACTIVIDAD ECONÓMICA"),
               "4": _detail("4", fin="2026-11-01"), "5": _detail("5", nivel="LOCAL", region="ES41 - CASTILLA Y LEÓN"),
               "6": _detail("6", nivel="AUTONOMICA", region="ES30 - COMUNIDAD DE MADRID")}
    def fake(url, params=None, **kw):
        if url.endswith("/busqueda"):
            return {"content": [{"numeroConvocatoria": n, "descripcion": f"Ayudas a emprendedores {n}", "fechaRecepcion": "2026-11-20",
                                 "nivel1": details[n]["organo"]["nivel1"]} for n in details]}
        return details[params["numConv"]]
    monkeypatch.setattr(B.net, "get_json", fake)
    g = B.grants({"country": "ES"}, NOW)
    assert [x["id"] for x in g] == ["gr1", "gr6"] and g[0]["ambito"] == "estatal"
    g = B.grants({"country": "ES", "subregion": "Castilla y León"}, NOW)
    assert {x["id"] for x in g} == {"gr1", "gr5", "gr6"}
    assert B.grants({"country": "EG"}, NOW) == []


def test_clean_brief_drops_invented_things():
    raw = {"resumen": "Hoy, una ronda y nada más.",
           "secciones": {"startups": {"picks": [{"ref": "st1", "titulo": "Acme", "fuentes": ["https://inventado.example/x", "https://startupxplore.com/es/a/"]},
                                                {"ref": "st99", "titulo": "Sin respaldo", "fuentes": ["https://otra.example"]},
                                                {"ref": None, "titulo": "Encontrada en la web", "fuentes": ["https://crowdcube.com/c/abc?utm=1"]}],
                                      "nota": ""},
                         "accion": {"picks": [{"ref": "ZZZZ", "titulo": "Una acción inventada"}], "nota": "ninguna"},
                         "clonar": {"picks": [{"titulo": "Idea"} for _ in range(5)]}}}
    out = B.clean_brief(raw, refs={"startups": {"st1"}, "accion": {"STNG"}},
                        allowed_urls={"https://startupxplore.com/es/a", "https://www.crowdcube.com/c/abc"})
    st = out["secciones"]["startups"]["picks"]
    assert [p["titulo"] for p in st] == ["Acme", "Encontrada en la web"]
    assert st[0]["fuentes"] == ["https://startupxplore.com/es/a/"] and st[1]["ref"] is None
    assert out["secciones"]["accion"]["picks"] == [] and out["secciones"]["clonar"]["picks"] == []
    assert out["descartados_por_validacion"] == 6 and set(out["secciones"]) == set(B.SECTIONS)


def test_slots_and_check_due(tmp_path):
    times = ["07:30", "19:00"]
    assert B.slots_due(None, NOW, times)
    assert not B.slots_due(datetime(2026, 11, 24, 6, 40, tzinfo=timezone.utc), NOW, times)  # informe de las 07:40 en Madrid
    assert B.slots_due(datetime(2026, 11, 23, 18, 30, tzinfo=timezone.utc), NOW, times)    # el de anoche: ya tocan las 07:30
    assert not B.slots_due(datetime(2026, 11, 23, 18, 30, tzinfo=timezone.utc), datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc), times)
    (tmp_path / "brief.json").write_text(json.dumps({"checkedAt": "2026-11-23T18:30:00Z", "attemptedAt": "2026-11-24T06:45:00Z"}))
    assert not B.check_due(tmp_path, {}, NOW)  # hubo un intento hace 15 min
    (tmp_path / "brief.json").write_text(json.dumps({"checkedAt": "2026-11-23T18:30:00Z", "attemptedAt": "2026-11-23T18:30:00Z"}))
    assert B.check_due(tmp_path, {}, NOW)


POOL = {"startups": [{"id": "st1", "plataforma": "Startupxplore", "empresa": "ACME", "url": "https://startupxplore.com/es/inversores/invertir-startups/acme"}],
        "clonar": [{"id": "cl1", "fuente": "TrustMRR", "nombre": "Leadly", "url": "https://trustmrr.com/startup/leadly"}],
        "accion": [{"id": "STNG", "ticker": "STNG", "tipo_senal": "ruptura", "url": "https://finance.yahoo.com/quote/STNG"}], "accion_ctx": {},
        "extra": [{"id": "lst:coinbase:abc", "titular": "Coinbase lista ABC", "url": "https://x.example/abc"}]}
REPLY = {"resumen": "Una ronda con ticket de 500 € y una idea para clonar.",
         "secciones": {"startups": {"picks": [{"ref": "st1", "titulo": "Acme Robots", "pasos": ["Abre la ficha"], "confianza": "media",
                                               "fuentes": ["https://news.example/acme"]}], "nota": ""},
                       "clonar": {"picks": [{"ref": "cl1", "titulo": "Leads para clínicas dentales", "confianza": "alta"}], "nota": ""},
                       "accion": {"picks": [], "nota": "Ninguna rompe con volumen."}, "ayudas": {"picks": [], "nota": ""},
                       "extra": {"picks": [], "nota": ""}},
         "descartado": "Bonos y biotecnología: ticket o riesgo fuera de tu perfil."}


class FakeResp:
    def __init__(self, d):
        self.d = d

    def json(self):
        return self.d


def _setup(monkeypatch, tmp_path, *, key=True):
    monkeypatch.setattr(B, "gather", lambda data_dir, feed, now: {k: (list(v) if isinstance(v, list) else v) for k, v in POOL.items()})
    monkeypatch.setattr(B, "grants", lambda prof, now: [])
    sent = []
    monkeypatch.setattr(B.notify, "send", lambda title, msg, **kw: sent.append((title, msg)) or True)
    if key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("NTFY_TOPIC", "radar-test")
    calls = []

    def transport(method, url, headers=None, json=None, **kw):
        calls.append(json)
        assert url == B.API and headers["x-api-key"] == "test-key" and json["model"] == "claude-opus-5-5"
        assert json["output_config"]["effort"] == "medium" and json["tools"][0]["max_uses"] == 3
        assert json["system"][1]["cache_control"] == {"type": "ephemeral"}
        content = [{"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "acme"}},
                   {"type": "web_search_tool_result", "tool_use_id": "s1", "content": [{"type": "web_search_result", "url": "https://news.example/acme", "title": "A"}]},
                   {"type": "text", "text": "```json\n" + __import__("json").dumps(REPLY) + "\n```"}]
        return FakeResp({"type": "message", "content": content, "stop_reason": "end_turn",
                         "usage": {"input_tokens": 12000, "output_tokens": 5000, "cache_read_input_tokens": 0, "server_tool_use": {"web_search_requests": 2}}})
    cfg = {"profiles": [{"id": "es", "name": "España", "country": "ES", "language": "es", "notify": "NTFY_TOPIC"}],
           "brief": {"max_searches": 3}}
    return cfg, transport, calls, sent


def test_run_with_claude(monkeypatch, tmp_path):
    cfg, transport, calls, sent = _setup(monkeypatch, tmp_path)
    out = B.run(tmp_path, cfg, now=NOW, transport=transport)
    p = out["profiles"]["es"]
    assert p["ok"] and p["provider"] == "anthropic" and p["searches"] == 2
    assert p["cost_usd"] == pytest.approx(12000 * 4 / 1e6 + 5000 * 20 / 1e6 + 0.02)
    st = p["secciones"]["startups"]["picks"][0]
    assert st["fuentes"] == ["https://news.example/acme"] and st["enlace"] == POOL["startups"][0]["url"]
    assert p["secciones"]["clonar"]["picks"][0]["enlace"] == "https://trustmrr.com/startup/leadly"
    assert p["secciones"]["accion"]["nota"].startswith("Ninguna") and len(sent) == 1 and "Acme Robots" in sent[0][1]
    saved = json.loads((tmp_path / "brief.json").read_text())
    assert saved["spend"]["usd"] == pytest.approx(p["cost_usd"]) and saved["profiles"]["es"]["fingerprint"]
    # segunda vuelta sin cambios en los candidatos: no se llama a Claude ni se avisa otra vez
    B.run(tmp_path, cfg, now=NOW.replace(hour=18), transport=transport)
    assert len(calls) == 1 and len(sent) == 1
    # con --force sí
    B.run(tmp_path, cfg, now=NOW.replace(hour=19), transport=transport, force=True)
    assert len(calls) == 2


def test_run_pause_turn_is_continued(monkeypatch, tmp_path):
    cfg, transport, calls, sent = _setup(monkeypatch, tmp_path)
    state = {"n": 0}

    def paused(method, url, headers=None, json=None, **kw):
        state["n"] += 1
        if state["n"] == 1:
            return FakeResp({"type": "message", "stop_reason": "pause_turn", "usage": {"input_tokens": 100, "output_tokens": 10},
                             "content": [{"type": "web_search_tool_result", "content": [{"url": "https://news.example/acme"}]}]})
        assert json["messages"][-1]["role"] == "assistant"
        return transport(method, url, headers=headers, json=json)
    out = B.run(tmp_path, cfg, now=NOW, transport=paused)
    assert out["profiles"]["es"]["ok"] and state["n"] == 2


def test_fallback_without_key_and_over_cap(monkeypatch, tmp_path):
    cfg, transport, calls, sent = _setup(monkeypatch, tmp_path, key=False)
    seen = []
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("GROQ_API_KEY", "q")
    cfg["limits"] = {"max_llm_calls": {"gemini": 40, "groq": 60}}
    cfg["models"] = {"gemini_preference": ["gemini-a", "gemini-b"]}

    def fake_ask(self, provider, system, prompt, **kw):
        seen.append((provider, self.chosen.get(provider), len(system)))
        if provider == "gemini" and self.chosen["gemini"] == "gemini-a":
            raise RuntimeError("HTTP 503")  # sobrecargado: prueba el siguiente modelo
        return {"data": REPLY, "model": self.chosen.get(provider) or provider, "provider": provider}
    monkeypatch.setattr(B.Router, "ask", fake_ask)
    out = B.run(tmp_path, cfg, now=NOW, transport=transport)
    p = out["profiles"]["es"]
    assert p["provider"] == "gemini" and p["model"] == "gemini-b" and p["cost_usd"] == 0 and [x[:2] for x in seen] == [("gemini", "gemini-a"), ("gemini", "gemini-b")]
    assert p["secciones"]["startups"]["picks"][0]["fuentes"] == []  # sin búsqueda: no hay enlaces de fuera que validar
    assert not calls
    # con clave pero el tope de hoy ya gastado → respaldo gratuito
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    data = json.loads((tmp_path / "brief.json").read_text())
    data["spend"] = {"date": "2026-11-24", "usd": 1.2}
    (tmp_path / "brief.json").write_text(json.dumps(data))
    out = B.run(tmp_path, cfg, now=NOW.replace(hour=19), transport=transport, force=True)
    assert out["profiles"]["es"]["provider"] == "gemini" and "tope diario" in out["profiles"]["es"]["error"] and not calls


def test_free_fallback_uses_short_prompt_for_groq(monkeypatch, tmp_path):
    cfg, transport, calls, sent = _setup(monkeypatch, tmp_path, key=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "q")
    cfg["limits"] = {"max_llm_calls": {"groq": 60}}
    seen = []

    def fake_ask(self, provider, system, prompt, **kw):
        seen.append((provider, system))
        return {"data": REPLY, "model": "openai/gpt-oss-120b", "provider": provider}
    monkeypatch.setattr(B.Router, "ask", fake_ask)
    out = B.run(tmp_path, cfg, now=NOW, transport=transport)
    assert out["profiles"]["es"]["provider"] == "groq" and seen[0][0] == "groq" and "CANDIDATOS (resumidos)" in seen[0][1]


def test_breakout_signal():
    random.seed(3)
    c = [100 + random.uniform(-3, 3) for _ in range(200)]
    h, v = [x + 1 for x in c], [1e6] * 200
    c2, h2, v2 = c + [104.8, 106.0], h + [105.2, 106.4], v + [1.3e6, 2.4e6]
    b = M.detect_breakout(c2, h2, v2)
    assert b and b["type"] == "ruptura" and b["volx"] == 2.4 and b["text"].startswith("Rompe su máximo de 6 meses")
    assert M.detect_trigger(c2, h2, [x - 1 for x in c2], v2)["type"] == "ruptura"
    assert M.detect_breakout(c + [104.8, 106.0], h2, v + [1e6, 1.1e6]) is None  # sin volumen no hay ruptura
    assert M.detect_breakout(c + [104.8, 120.0], h2[:-1] + [120.5], v2) is None  # demasiado estirada para entrar
