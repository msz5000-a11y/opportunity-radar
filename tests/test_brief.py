"""Pruebas del informe «Para ti» (radar/brief.py) y de la señal de ruptura del radar de mercados."""
import json
import random
from datetime import datetime, timedelta, timezone
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
               "4": _detail("4", fin="2026-11-01"),
               "6": _detail("6", nivel="AUTONOMICA", region="ES52 - COMUNIDAD VALENCIANA"),
               "7": _detail("7", nivel="LOCAL", region="ES523 - Valencia / València", fin="2026-12-10"),
               "8": _detail("8", nivel="LOCAL", region="ES523 - Valencia / València", fin="2026-12-20")}
    rows = lambda nums: {"content": [{"numeroConvocatoria": n, "descripcion": f"Ayudas a emprendedores {n}", "fechaRecepcion": "2026-11-20",  # noqa: E731
                                      "nivel1": details[n]["organo"]["nivel1"]} for n in nums]}

    def fake(url, params=None, **kw):
        if url.endswith("/busqueda"):
            if params.get("organos") == 2611:
                return rows(["7"])
            if params.get("organos") == 638:
                return rows(["8"])
            if params.get("regiones") == 54:
                return rows(["6"])
            return rows(["1", "2", "3", "4", "6", "7"])  # la búsqueda general: solo cuentan las del Estado
        return details[params["numConv"]]
    monkeypatch.setattr(B.net, "get_json", fake)
    B._GRANT_CACHE.clear()
    g = B.grants({"country": "ES"}, NOW)
    assert [x["id"] for x in g] == ["gr1"] and g[0]["ambito"] == "estatal"
    B._GRANT_CACHE.clear()
    ids = {"region": 54, "diputacion": 638, "diputacion_name": "DIPUTACIÓN PROVINCIAL DE VALENCIA",
           "ayuntamiento": 2611, "ayuntamiento_name": "AYUNTAMIENTO DE RIBA-ROJA DE TÚRIA"}
    g = B.grants({"country": "ES"}, NOW, ids)
    assert [x["id"] for x in g] == ["gr7", "gr8", "gr6", "gr1"]
    assert [x["ambito"] for x in g] == ["municipal", "provincial", "autonomica", "estatal"] and g[0]["donde"] == "AYUNTAMIENTO DE RIBA-ROJA DE TÚRIA"
    assert B.grants({"country": "EG"}, NOW) == []


def test_bdns_ids_resolve_and_cache(monkeypatch, tmp_path):
    regs = [{"id": 1, "descripcion": "ES - ESPAÑA ", "children": [{"id": 50, "descripcion": "ES5 - ESTE", "children": [
        {"id": 54, "descripcion": "ES52 - COMUNIDAD VALENCIANA", "children": [{"id": 57, "descripcion": "ES523 - Valencia / València"}]}]}]}]
    orgs = [{"id": 99, "descripcion": "VALÈNCIA / VALENCIA", "children": [
        {"id": 2774, "descripcion": "RIBA-ROJA DE TÚRIA", "children": [{"id": 2611, "descripcion": "AYUNTAMIENTO DE RIBA-ROJA DE TÚRIA"}]}]},
        {"id": 2559, "descripcion": "DIPUTACIÓN PROV. DE VALENCIA", "children": [{"id": 638, "descripcion": "DIPUTACIÓN PROVINCIAL DE VALENCIA"}]}]
    calls = []

    def fake(url, params=None, **kw):
        calls.append(url)
        return regs if url.endswith("/regiones") else orgs
    monkeypatch.setattr(B.net, "get_json", fake)
    prof = {"country": "ES", "region": "ES52", "province": "Valencia", "municipality": "Riba-roja de Túria"}
    ids = B.bdns_ids(prof, tmp_path)
    assert (ids["region"], ids["diputacion"], ids["ayuntamiento"]) == (54, 638, 2611)
    assert B.bdns_ids(prof, tmp_path) == ids and len(calls) == 2  # la segunda vez sale de data/bdns_ids.json
    assert B.bdns_ids({"country": "EG"}, tmp_path) == {}


RSS = """<rss><channel><item><title>How a Former Math Teacher Reached $10,000 a Month Selling Printables on Etsy - StreetInsider</title>
<link>https://news.google.com/rss/articles/abc</link><pubDate>Tue, 17 Nov 2026 10:00:00 GMT</pubDate><source url="https://streetinsider.com">StreetInsider</source></item>
<item><title>How a Former Math Teacher Reached $10,000 a Month Selling Printables on Etsy - Otro</title><link>https://news.google.com/rss/articles/dup</link>
<pubDate>Tue, 17 Nov 2026 10:00:00 GMT</pubDate><source url="https://x">Otro</source></item></channel></rss>"""


def test_home_stories_and_ideas(monkeypatch):
    seen_q = []
    monkeypatch.setattr(B, "_get", lambda url, **kw: seen_q.append(url) or RSS)
    st = B.home_stories({"interests": ["diseño", "niños"]})
    assert [x["titular"] for x in st] == ["How a Former Math Teacher Reached $10,000 a Month Selling Printables on Etsy"]
    assert st[0]["medio"] == "StreetInsider" and st[0]["url"] == "https://news.google.com/rss/articles/abc"
    assert any("design" in q for q in seen_q) and any("kids" in q for q in seen_q)
    raw = {"ideas": [{"titulo": "Láminas imprimibles para habitaciones infantiles", "gancho": "Diseña una vez, vende mil veces",
                      "casos": [{"quien": "Profesora en Izmir", "pais": "Turquía", "resultado": "10.000 $ en un mes en Etsy", "url": "https://news.google.com/rss/articles/abc"},
                                {"quien": "Inventada", "pais": "X", "resultado": "1M", "url": "https://inventado.example"}],
                      "como_empezar": ["Semana 1: abre la tienda"], "ayudas": ["gr1", "gr999"], "confianza": "alta"},
                     {"titulo": "Idea sin casos", "casos": []},
                     {"titulo": "Repetida", "casos": [{"url": "https://news.google.com/rss/articles/abc"}]}],
           "oportunidades_locales": [{"titulo": "Mercado artesano", "url": "https://inventado.example/m"}], "nota": "ok"}
    got = B.clean_ideas(raw, allowed_urls={"https://news.google.com/rss/articles/abc"}, grant_ids={"gr1"}, prev_titles=["Repetida"], now=NOW)
    assert [i["titulo"] for i in got["ideas"]] == ["Láminas imprimibles para habitaciones infantiles"]
    i = got["ideas"][0]
    assert len(i["casos"]) == 1 and i["ayudas"] == ["gr1"] and i["nueva"] and got["oportunidades_locales"] == [] and got["descartadas"] == 2


def test_casa_due_and_profiles(tmp_path):
    prof = {"id": "ella", "interests": ["arte"], "casa": True}
    assert B.casa_due({}, prof, NOW)
    old = {"ideas": [{"titulo": "x"}], "generatedAt": "2026-11-23T07:00:00Z", "checkedAt": "2026-11-24T05:30:00Z", "profile_hash": B.profile_hash(prof)}
    assert not B.casa_due(old, prof, NOW)  # la última tanda fue hace hora y media: aún no toca (cada 3 h)
    assert B.casa_due(old, {**prof, "interests": ["arte", "cocina"]}, NOW)  # perfil cambiado: ideas nuevas
    assert B.casa_due({**old, "checkedAt": "2026-11-24T03:30:00Z"}, prof, NOW)
    (tmp_path / "profiles.json").write_text(json.dumps({"profiles": [{"id": "es"}, {"id": "off", "off": True}, {"id": "ella"}]}))
    assert [p["id"] for p in B.load_profiles(tmp_path, {})] == ["es", "ella"]


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
    cfg["brief"] = {**cfg.get("brief", {}), "free_models": ["gemini-a", "gemini-b"]}

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


def test_stock_needs_a_real_breakout_and_facts_come_from_the_source(monkeypatch, tmp_path):
    cfg, transport, calls, sent = _setup(monkeypatch, tmp_path)
    pool = json.loads(json.dumps(POOL))
    pool["startups"][0].update({"ticket_min_eur": 500, "cierre": "2026-12-20", "completado_pct": 40.2})
    pool["accion"] = [{"id": "STNG", "ticker": "STNG", "tipo_senal": None, "senal": None, "precio_usd": 78.06},
                      {"id": "ACME", "ticker": "ACME", "tipo_senal": "ruptura", "senal": "Rompe su máximo de 6 meses (50,00 $)", "precio_usd": 51.2,
                       "tecnico": {"stop": 46.1}, "valor_razonable_usd": [60, 70], "metricas": {"pe": 11.2}}]
    monkeypatch.setattr(B, "gather", lambda data_dir, feed, now: pool)
    reply = json.loads(json.dumps(REPLY))
    reply["resumen"] = "Dos acciones con ruptura y una ronda."
    reply["secciones"]["startups"]["picks"][0]["datos"] = {"Ticket mínimo": "100 €", "Equipo": "3 personas"}
    reply["secciones"]["accion"]["picks"] = [{"ref": "STNG", "titulo": "Scorpio Tankers"}]

    def t2(method, url, headers=None, json=None, **kw):
        r = transport(method, url, headers=headers, json=json)
        r.d["content"][-1]["text"] = __import__("json").dumps(reply)
        return r
    out = B.run(tmp_path, cfg, now=NOW, transport=t2)
    p = out["profiles"]["es"]
    assert p["secciones"]["accion"]["picks"] == []  # STNG no rompe al alza: fuera
    assert p["resumen"].startswith("Hoy para ti: 1 ronda abierta que encaja contigo") and "ninguna acción infravalorada rompe al alza" in p["resumen"]
    d = p["secciones"]["startups"]["picks"][0]["datos"]
    assert d["Ticket mínimo"] == "500 €" and d["Plataforma"] == "Startupxplore" and d["Completado"] == "40.2 %" and d["Equipo"] == "3 personas"
    # la de verdad sí entra, con los datos del radar
    reply["secciones"]["accion"]["picks"] = [{"ref": "ACME", "titulo": "Acme", "datos": {"Señal": "inventada"}}]
    out = B.run(tmp_path, cfg, now=NOW, transport=t2, force=True)
    a = out["profiles"]["es"]["secciones"]["accion"]["picks"][0]
    assert a["datos"]["Señal"].startswith("Rompe su máximo") and a["datos"]["Stop"] == "46.1 $" and a["datos"]["Valor razonable"] == "60-70 $"


def test_run_with_home_ideas_profile(monkeypatch, tmp_path):
    cfg, transport, calls, sent = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("NTFY_TOPIC_ELLA", "radar-ella")
    (tmp_path / "profiles.json").write_text(json.dumps({"profiles": [
        {"id": "ella", "name": "Ella", "emoji": "🏡", "language": "es", "country": "ES", "interests": ["diseño", "niños"],
         "sections": ["ayudas", "extra"], "casa": True, "start_tab": "casa", "notify": "NTFY_TOPIC_ELLA"}]}))
    monkeypatch.setattr(B, "bdns_ids", lambda prof, d: {})
    monkeypatch.setattr(B, "grants", lambda prof, now, ids=None: [{"id": "gr5", "titulo": "Ayuda a emprendedoras", "url": "https://www.infosubvenciones.es/x/5",
                                                                    "donde": "Estado", "ambito": "estatal", "solicitud": {"hasta": "2026-12-31"}}])
    monkeypatch.setattr(B, "home_stories", lambda prof, **kw: [{"id": "hs1", "titular": "Teacher earns $10k selling printables", "url": "https://news.example/story"},
                                                                {"id": "hs2", "titular": "Mum launched meal plans business, now earns $4k a month", "url": "https://news.example/meals"}])
    monkeypatch.setattr(B, "trust_for", lambda prof: [])
    idea_reply = {"ideas": [{"titulo": "Láminas infantiles personalizadas", "gancho": "Diseño a medida para habitaciones",
                             "casos": [{"quien": "Profesora", "pais": "Turquía", "resultado": "10.000 $ en un mes", "url": "https://news.example/story"}],
                             "como_empezar": ["Semana 1: 5 diseños"], "ayudas": ["gr5"], "confianza": "alta"}],
                  "oportunidades_locales": [{"titulo": "Programa de la Cámara", "url": "https://camara.example/p"}], "nota": "ok"}
    brief_reply = {"resumen": "Una ayuda.", "secciones": {"ayudas": {"picks": [{"ref": "gr5", "titulo": "Ayuda a emprendedoras"}], "nota": ""},
                                                          "extra": {"picks": [], "nota": ""}, "accion": {"picks": [{"ref": "STNG", "titulo": "no pedida"}]}}}
    systems = []

    def t3(method, url, headers=None, json=None, **kw):
        sysx = json["system"][0]["text"]
        systems.append("casa" if sysx == B.RULES_CASA else "brief")
        reply = idea_reply if sysx == B.RULES_CASA else brief_reply
        content = [{"type": "web_search_tool_result", "content": [{"url": "https://camara.example/p"}]},
                   {"type": "text", "text": __import__("json").dumps(reply)}]
        if sysx == B.RULES_CASA:
            assert json["tools"][0]["max_uses"] == 4 and "IDEAS ANTERIORES" in json["messages"][0]["content"]
            assert json["model"] == "claude-haiku-5-5" and "output_config" not in json  # tandas frecuentes con el modelo barato
        else:
            assert "## STARTUPS" not in json["system"][1]["text"] and "## PULSO" in json["system"][1]["text"]
        calls.append(json)
        return FakeResp({"type": "message", "content": content, "stop_reason": "end_turn", "usage": {"input_tokens": 9000, "output_tokens": 4000}})
    out = B.run(tmp_path, cfg, now=NOW, transport=t3)
    p = out["profiles"]["ella"]
    assert systems == ["brief", "casa"] and set(p["secciones"]) == {"ayudas", "extra"}  # la sección no pedida no aparece
    assert p["profile"]["start_tab"] == "casa" and p["casa"]["nuevas"] == 1 and p["casa"]["ideas"][0]["ayudas"] == ["gr5"]
    assert p["casa"]["oportunidades_locales"][0]["url"] == "https://camara.example/p" and p["casa"]["ayudas"][0]["id"] == "gr5"
    case = p["casa"]["ideas"][0]["casos"][0]
    assert case["resultado"] == "Teacher earns $10k selling printables" and case["pais"] == ""  # el texto del caso sale de la fuente
    assert any("Ideas nuevas desde casa" in t for t, m in sent)
    # una hora después en modo automático: ni informe (ya es de hoy) ni ideas (cada 3 h)
    B.run(tmp_path, cfg, now=NOW.replace(hour=8), transport=t3, mode="auto")
    assert systems == ["brief", "casa"]
    # con «Más ideas» (modo casa + force) sí, aunque no hayan pasado 3 h
    idea_reply["ideas"][0]["titulo"] = "Menús semanales para familias"
    out = B.run(tmp_path, cfg, now=NOW.replace(hour=9), transport=t3, mode="casa", force=True)
    assert systems == ["brief", "casa", "casa"] and out["profiles"]["ella"]["casa"]["motivos"]["sin_caso"] == 1  # el caso ya usado no vale otra vez
    idea_reply["ideas"][0]["casos"][0]["url"] = "https://news.example/meals"
    out = B.run(tmp_path, cfg, now=NOW.replace(hour=9, minute=30), transport=t3, mode="casa", force=True)
    ideas = out["profiles"]["ella"]["casa"]["ideas"]
    assert [i["titulo"] for i in ideas] == ["Menús semanales para familias", "Láminas infantiles personalizadas"] and not ideas[1]["nueva"]


def test_grant_relevance():
    assert not B.grant_relevant("MH Convocatoria Premio María la Jabalina de Memoria Democrática 2027", "Justicia")
    assert not B.grant_relevant("Subvenciones a clubes deportivos 2026", "Deportes")
    assert B.grant_relevant("Ayudas al fomento del emprendimiento 2026", None)
    assert B.grant_relevant("Premio a la empresa emprendedora del año", None)
    assert B.grant_relevant("Convocatoria Go Digital Comarcas 2026", "Comercio, Turismo y Pymes")


def test_auto_mode_runs_ideas_every_few_hours(monkeypatch, tmp_path):
    cfg, transport, calls, sent = _setup(monkeypatch, tmp_path)
    (tmp_path / "profiles.json").write_text(json.dumps({"profiles": [{"id": "ella", "language": "es", "country": "ES", "interests": ["arte"],
                                                                      "sections": [], "casa": True}]}))
    monkeypatch.setattr(B, "bdns_ids", lambda prof, d: {})
    monkeypatch.setattr(B, "grants", lambda prof, now, ids=None: [])
    monkeypatch.setattr(B, "home_stories", lambda prof, **kw: [{"id": f"hs{i}", "titular": f"Story {i}", "url": f"https://news.example/s{i}"} for i in (1, 2)])
    monkeypatch.setattr(B, "trust_for", lambda prof: [])
    n = {"calls": 0}

    def t(method, url, headers=None, json=None, **kw):
        n["calls"] += 1
        reply = {"ideas": [{"titulo": f"Idea {n['calls']}", "casos": [{"url": f"https://news.example/s{n['calls']}"}], "temas": ["arte"]}]}
        return FakeResp({"type": "message", "content": [{"type": "text", "text": __import__("json").dumps(reply)}], "stop_reason": "end_turn", "usage": {}})
    B.run(tmp_path, cfg, now=NOW, transport=t, mode="auto")
    assert n["calls"] == 1 and not B.check_due(tmp_path, cfg, NOW.replace(hour=8))
    assert B.check_due(tmp_path, cfg, NOW.replace(hour=10, minute=5))  # tres horas después toca otra tanda
    out = B.run(tmp_path, cfg, now=NOW.replace(hour=10, minute=5), transport=t, mode="auto")
    ideas = out["profiles"]["ella"]["casa"]["ideas"]
    assert n["calls"] == 2 and [i["titulo"] for i in ideas] == ["Idea 2", "Idea 1"] and ideas[0]["temas"] == ["arte"]


def test_feed_home_and_focus(tmp_path):
    feed = {"items": [
        {"id": "hc:1", "cat": "casa", "kind": "story", "pf": ["ella"], "title": "Mum earns $5k a month from home bakery", "es": "Una madre gana 5.000 dólares al mes con su obrador en casa",
         "src": "BBC", "url": "https://news.google.com/a", "w": "2026-11-23T10:00:00Z", "pub": "2026-11-23T10:00:00Z", "lang": "en"},
        {"id": "hc:2", "cat": "casa", "kind": "local", "pf": ["ella"], "title": "Riba-roja abre un curso gratuito de comercio online", "src": "Levante",
         "url": "https://news.google.com/b", "w": "2026-11-22T10:00:00Z", "why": "Formación gratis cerca de casa"},
        {"id": "hc:3", "cat": "casa", "kind": "story", "pf": ["eg"], "title": "Other profile", "url": "https://news.google.com/c", "w": "2026-11-23T11:00:00Z"},
        {"id": "hc:4", "cat": "casa", "kind": "story", "pf": ["ella"], "h": 1, "title": "Hidden", "url": "https://news.google.com/d", "w": "2026-11-23T12:00:00Z"},
        {"id": "n:1", "cat": "cripto", "kind": "news", "title": "BTC", "url": "https://x"}]}
    fp = tmp_path / "feed.json"
    fp.write_text(json.dumps(feed))
    stories, local = B.feed_home(fp, {"id": "ella"})
    assert [x["url"] for x in stories] == ["https://news.google.com/a"] and stories[0]["titular_es"].startswith("Una madre") and stories[0]["medio"] == "BBC"
    assert local == [{"id": "hl1", "titulo": "Riba-roja abre un curso gratuito de comercio online", "medio": "Levante", "fecha": "2026-11-22",
                      "por_que": "Formación gratis cerca de casa", "url": "https://news.google.com/b"}]
    prof = {"interests": ["inmobiliaria", "arte", "cocina"]}
    prev = [{"temas": ["inmobiliaria"]}, {"temas": ["Inmobiliaria", "arte"]}]
    assert B.casa_focus(prof, prev, 0) == ["cocina", "arte"]
    assert B.casa_focus(prof, [], 1) == ["arte", "cocina"] and B.casa_focus(prof, [], 2) == ["cocina", "inmobiliaria"]  # empates: va rotando


def test_notify_casa_throttled(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC_ELLA", "radar-ella")
    sent = []
    monkeypatch.setattr(B.notify, "send", lambda title, msg, **kw: sent.append((title, msg)) or True)
    prof = {"id": "ella", "name": "Ella", "notify": "NTFY_TOPIC_ELLA"}
    casa = {"ideas": [{"titulo": f"Idea {i}", "gancho": "g", "fecha": B.iso(NOW)} for i in range(5)]}
    B.notify_casa(prof, casa, NOW)
    assert len(sent) == 1 and "… y 2 más" in sent[0][1] and casa["notifiedAt"] == B.iso(NOW)
    B.notify_casa(prof, casa, NOW + timedelta(hours=3))  # otra tanda a las 3 horas: sin aviso
    casa["ideas"].insert(0, {"titulo": "Idea nueva", "gancho": "g", "fecha": B.iso(NOW + timedelta(hours=9))})
    B.notify_casa(prof, casa, NOW + timedelta(hours=9))
    assert len(sent) == 2 and "Idea nueva" in sent[1][1] and "Idea 0" not in sent[1][1]
    B.notify_casa(prof, {"ideas": casa["ideas"]}, NOW.replace(hour=23))  # de noche, nunca
    assert len(sent) == 2
