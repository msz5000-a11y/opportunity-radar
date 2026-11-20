import copy
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from radar.scoring import run, fingerprint, CRITERIA

NOW = "2026-11-20T00:00:00+00:00"


def full(v=8, ev=True):
    return {k: {"v": v, "why": "x", "evidence": ev} for k, _, _ in CRITERIA}


def base(**kw):
    c = {"name": "Proyecto X", "category": "ia_tecnologia", "subcategory": "beta",
         "officialUrl": "https://www.proyectox.ai/", "spainAvailability": "si",
         "costs": {"minEntry": 0, "extra": 0, "recommended": 0}, "canLoseAll": False,
         "kind": "activa", "subscores": full()}
    c.update(kw)
    return c


def one(c, existing=None, profile=None):
    p = {"profile": profile or {"budget": 150}, "now": NOW, "fx": {"usdToEur": 0.9},
         "candidates": [c], "existing": existing or {}}
    r = run(p)
    assert not r["errors"], r["errors"]
    return r["results"][0]


def test_weights_and_tier():
    r = one(base())
    assert r["score"] == 80 and r["tier"] == "prometedora"
    assert r["alert"]["level"] == "normal"


def test_no_evidence_caps():
    r = one(base(subscores=full(9, ev=False)))
    assert r["score"] <= 30  # cada criterio sin evidencia vale como máximo 3
    s = full(10)
    for k in list(s)[:7]:
        s[k]["evidence"] = False
    r = one(base(subscores=s))
    assert r["score"] <= 59


def test_critical_flag_caps_and_no_alert():
    r = one(base(redFlags=[{"code": "suplantacion", "severity": "critica", "detail": "web clonada"}]))
    assert r["score"] <= 20 and r["critical"] and r["risk"] == "crítico"
    assert r["alert"]["level"] == "ninguna"


def test_honeypot_from_market():
    c = base(category="cripto", canLoseAll=True,
             market={"chain": "base", "tokenAddress": "0xABC", "liquidityUsd": 50000, "volume24hUsd": 20000,
                     "fdvUsd": 400000, "buys24h": 120, "sells24h": 0})
    r = one(c)
    assert any(f["code"] == "posible_honeypot" for f in r["flags"]) and r["score"] <= 20
    assert r["id"] == "tok-base-0xabc"


def test_regulatory_and_spain():
    r = one(base(regulatory={"status": "advertencia_cnmv", "notes": "Advertencia CNMV"}))
    assert r["critical"]
    r = one(base(spainAvailability="no"))
    assert r["score"] <= 39


def test_budget_cap():
    r = one(base(costs={"minEntry": 500}))
    assert r["score"] <= 39


def test_scenarios_exit_realism():
    c = base(category="cripto", canLoseAll=True, costs={"minEntry": 20, "extra": 3, "recommended": 50},
             market={"chain": "sol", "tokenAddress": "Mint1", "liquidityUsd": 20000, "fdvUsd": 5_000_000,
                     "volume24hUsd": 10000, "buys24h": 100, "sells24h": 80})
    r = one(c)
    sc = r["scenarios"]
    assert sc["stakeEur"] == 50 and sc["lossScenarioEur"] == -53
    row300 = [x for x in sc["rows"] if x["multiple"] == 300][0]
    assert row300["grossEur"] == 15000 and row300["netEur"] < row300["grossEur"] * 0.5
    assert row300["realism"] and row300["exitNote"]


def test_dedupe_no_renotify_and_change():
    c = base()
    fid = fingerprint(c)
    r = one(c, existing={fid: {"score": 80, "notifiedAt": NOW}})
    assert r["alert"]["level"] == "ninguna" and not r["isNew"]
    r = one(c, existing={fid: {"score": 65, "notifiedAt": NOW}})
    assert r["alert"]["level"] == "cambio"
    r = one(c, existing={fid: {"score": 10, "userAction": "descartada"}})
    assert r["alert"]["level"] == "ninguna"


def test_rug_detection_on_followed():
    c = base(category="cripto", canLoseAll=True,
             market={"chain": "eth", "tokenAddress": "0x1", "liquidityUsd": 20000, "buys24h": 10, "sells24h": 10})
    fid = fingerprint(c)
    ex = {fid: {"score": 70, "notifiedAt": NOW, "userAction": "guardada",
                "metrics": [{"t": "2026-11-19T00:00:00+00:00", "liquidityUsd": 200000}]}}
    r = one(c, existing=ex)
    assert r["momentum"]["label"] == "Retirada de liquidez"
    assert r["critical"] and r["alert"]["level"] == "urgente"


def test_urgent_with_deadline():
    c = base(subscores=full(9), deadline="2026-11-21T12:00:00Z")
    r = one(c)
    assert r["score"] == 90 and r["alert"]["level"] == "urgente" and r["humanReview"]


def test_alert_text_format():
    r = one(base(sources=[{"title": "a", "url": "https://a.com"}]))
    for field in ["NOMBRE:", "CATEGORÍA:", "FECHA DE DESCUBRIMIENTO:", "WEB OFICIAL:", "ENLACE DE PARTICIPACIÓN:",
                  "PAÍS:", "DISPONIBILIDAD EN ESPAÑA:", "COSTE DE ENTRADA:", "PRESUPUESTO RECOMENDADO:",
                  "POTENCIAL:", "PUNTUACIÓN:", "RIESGO:", "PLAZO:", "MOTIVO POR EL QUE PUEDE SER INTERESANTE:",
                  "MOTIVOS PARA DESCONFIAR:", "CÓMO PARTICIPAR:", "QUÉ PODRÍA HACERME PERDER EL DINERO:", "FUENTES:"]:
        assert field in r["alertText"], field


def test_bad_candidate_does_not_crash():
    out = run({"candidates": [{"name": "x", "category": "nope"}, base()], "now": NOW})
    assert len(out["errors"]) == 1 and len(out["results"]) == 1
