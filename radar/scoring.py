#!/usr/bin/env python3
"""
Opportunity Radar AI — motor de puntuación determinista.

Uso:
    python3 scoring.py entrada.json > salida.json

La investigación (búsqueda web, lectura de fuentes) la hace el agente.
Este módulo convierte lo investigado en una evaluación reproducible:
  * puntuación 0-100 a partir de 12 criterios ponderados,
  * topes obligatorios cuando hay riesgos críticos o falta de evidencias,
  * banderas de manipulación calculadas con datos de mercado,
  * escenarios 2x…300x (simulaciones, nunca predicciones),
  * comprobación de salida real (liquidez vs. capitalización),
  * decisión de alerta con deduplicación,
  * texto de alerta con el formato fijo pedido.

No ejecuta compras, no firma nada y no se conecta a ninguna wallet.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Criterios y pesos (suman 100). En los criterios de riesgo y competencia,
# un 10 significa "riesgo/competencia baja" (es decir, mejor).
# ---------------------------------------------------------------------------
CRITERIA = [
    ("novedad", "Novedad", 8),
    ("potencial", "Potencial de crecimiento", 12),
    ("mercado", "Tamaño del mercado", 8),
    ("equipo", "Calidad del equipo", 10),
    ("financiacion", "Financiación", 7),
    ("comunidad", "Comunidad", 7),
    ("adopcion", "Adopción", 9),
    ("competencia", "Competencia (10 = poca)", 5),
    ("riesgo_tecnico", "Riesgo técnico (10 = bajo)", 8),
    ("riesgo_financiero", "Riesgo financiero (10 = bajo)", 10),
    ("entrada_espana", "Facilidad de entrada desde España", 8),
    ("salida", "Posibilidad de salida o monetización", 8),
]
assert sum(w for _, _, w in CRITERIA) == 100

NO_EVIDENCE_MAX = 3          # un criterio sin evidencia no puede valer más de 3/10
MIN_EVIDENCED = 6            # con menos de 6 criterios con evidencia: tope 59
MULTIPLES = [2, 5, 10, 20, 50, 100, 300]
TIERS = [
    (90, "extraordinaria", "Extraordinariamente interesante · requiere revisión humana"),
    (75, "prometedora", "Oportunidad prometedora"),
    (60, "investigar", "Interesante, necesita investigación"),
    (40, "especulativa", "Especulativa"),
    (0, "descartar", "Descartar"),
]
CRITICAL_REG = {"advertencia_cnmv", "no_autorizada", "chiringuito"}
ALLOWED_CATEGORIES = {"cripto", "startups", "ia_tecnologia", "lanzamientos", "negocio"}


def _num(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def slugify(text: str, maxlen: int = 48) -> str:
    text = (text or "").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n"), ("ü", "u")):
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:maxlen].strip("-") or "sin-nombre"


def fingerprint(c: dict) -> str:
    """Identificador estable para no duplicar ni re-notificar la misma oportunidad."""
    m = c.get("market") or {}
    chain, addr = m.get("chain"), m.get("tokenAddress")
    if chain and addr:
        return slugify(f"tok-{chain}-{addr}", 70)
    url = c.get("officialUrl") or ""
    host = urlparse(url).netloc.lower().removeprefix("www.") if url else ""
    if host:
        path = urlparse(url).path.strip("/").split("/")
        # plataformas que alojan muchos proyectos: incluir la ruta
        hosted = ("github.com", "producthunt.com", "kickstarter.com", "indiegogo.com",
                  "crowdcube.com", "startupxplore.com", "verkami.com", "goteo.org", "x.com", "twitter.com")
        if any(host.endswith(h) for h in hosted) and path and path[0]:
            return slugify(f"web-{host}-{'-'.join(path[:2])}", 70)
        return slugify(f"web-{host}", 70)
    return slugify(f"n-{c.get('name', '')}", 70)


# ---------------------------------------------------------------------------
# Banderas calculadas a partir de datos de mercado
# ---------------------------------------------------------------------------
def market_flags(m: dict) -> list[dict]:
    flags = []
    if not m:
        return flags
    liq = _num(m.get("liquidityUsd"))
    vol = _num(m.get("volume24hUsd"))
    fdv = _num(m.get("fdvUsd")) or _num(m.get("mcapUsd"))
    age = _num(m.get("ageHours"))
    buys = _num(m.get("buys24h"))
    sells = _num(m.get("sells24h"))
    top10 = _num(m.get("top10Pct"))

    if buys is not None and sells is not None and buys >= 30 and sells == 0:
        flags.append({"code": "posible_honeypot", "severity": "critica",
                      "detail": f"{int(buys)} compras y 0 ventas en 24 h: patrón típico de honeypot (no se puede vender)."})
    elif buys is not None and sells is not None and buys >= 50 and sells / max(buys, 1) < 0.05:
        flags.append({"code": "ventas_bloqueadas", "severity": "alta",
                      "detail": f"Ventas anómalamente bajas ({int(sells)} frente a {int(buys)} compras)."})
    if liq is not None and liq < 10_000:
        flags.append({"code": "liquidez_minima", "severity": "alta",
                      "detail": f"Liquidez de solo {liq:,.0f} $: salir incluso con importes pequeños moverá mucho el precio."})
    if liq and vol is not None and vol / liq > 8:
        flags.append({"code": "posible_wash_trading", "severity": "alta",
                      "detail": f"Volumen 24 h {vol / liq:.0f} veces la liquidez: posible volumen artificial."})
    if liq and fdv and fdv / liq > 50:
        flags.append({"code": "fdv_inflada", "severity": "alta",
                      "detail": f"FDV {fdv / liq:.0f} veces la liquidez: la capitalización no es dinero retirable."})
    if top10 is not None and top10 > 50:
        flags.append({"code": "concentracion_tokens", "severity": "critica" if top10 > 80 else "alta",
                      "detail": f"Las 10 mayores carteras tienen el {top10:.0f}% del suministro."})
    if age is not None and age < 24:
        flags.append({"code": "muy_reciente", "severity": "media",
                      "detail": f"Creado hace {age:.0f} h: sin historial; la mayoría de tokens así acaban en cero."})
    return flags


def momentum(current: dict, history: list[dict]) -> dict:
    """Compara la instantánea actual con la anterior para detectar crecimiento temprano."""
    if not history:
        return {"available": False, "changes": {}, "label": "Primera observación"}
    prev = history[-1]
    changes = {}
    for k, v in current.items():
        if k in ("t",):
            continue
        a, b = _num(prev.get(k)), _num(v)
        if a and b is not None and a > 0:
            changes[k] = round((b - a) / a * 100, 1)
    label = "Estable"
    organic_keys = [k for k in ("holders", "stars", "followers", "members", "upvotes", "backers", "raisedEur", "liquidityUsd") if k in changes]
    if organic_keys and all(changes[k] > 15 for k in organic_keys):
        label = "Crecimiento acelerado"
    elif organic_keys and any(changes[k] > 15 for k in organic_keys):
        label = "Crecimiento"
    if "liquidityUsd" in changes and changes["liquidityUsd"] < -50:
        label = "Retirada de liquidez"
    if "volume24hUsd" in changes and changes["volume24hUsd"] > 300 and not any(changes.get(k, 0) > 10 for k in ("holders", "liquidityUsd")):
        label = "Pico de volumen sin adopción (sospechoso)"
    return {"available": True, "changes": changes, "label": label, "since": prev.get("t")}


# ---------------------------------------------------------------------------
# Escenarios y salida real
# ---------------------------------------------------------------------------
def scenarios(c: dict, stake_eur: float, usd_to_eur: float | None) -> dict:
    costs = c.get("costs") or {}
    extra = _num(costs.get("extra")) or 0.0
    m = c.get("market") or {}
    liq_usd = _num(m.get("liquidityUsd"))
    fdv_usd = _num(m.get("fdvUsd")) or _num(m.get("mcapUsd"))
    fee_pct = 0.01 if c.get("category") == "cripto" else 0.0
    rows = []
    for mult in MULTIPLES:
        gross = stake_eur * mult
        slip = 0.0
        exit_note = None
        if liq_usd and usd_to_eur:
            liq_eur = liq_usd * usd_to_eur
            # aproximación de pool de producto constante: impacto ≈ venta / (reserva lado estable)
            slip = min(0.99, gross / max(liq_eur / 2, 1))
            if gross > liq_eur * 0.02:
                exit_note = "Vender este importe movería el precio de forma significativa con la liquidez actual."
        net = gross * (1 - slip) * (1 - fee_pct) - extra
        row = {"multiple": mult, "grossEur": round(gross, 2), "netEur": round(net, 2),
               "exitImpactPct": round(slip * 100, 1), "exitNote": exit_note}
        if fdv_usd:
            implied = fdv_usd * mult
            row["impliedFdvUsd"] = round(implied)
            if implied >= 1e9:
                row["realism"] = "Exigiría superar 1.000 M$ de valoración total."
        rows.append(row)
    return {
        "stakeEur": round(stake_eur, 2),
        "extraCostsEur": round(extra, 2),
        "lossScenarioEur": round(-(stake_eur + extra), 2) if c.get("canLoseAll", True) else None,
        "rows": rows,
        "disclaimer": "Simulación matemática. No es una predicción ni una rentabilidad prometida, y no implica ninguna probabilidad.",
        "basis": "mercado" if fdv_usd else "capital",
    }


# ---------------------------------------------------------------------------
# Evaluación de una candidata
# ---------------------------------------------------------------------------
def evaluate(c: dict, profile: dict, existing: dict | None, now: str, fx: float | None) -> dict:
    budget = _num(profile.get("budget")) or 2000.0
    committed = _num(profile.get("committed")) or 0.0
    available = max(0.0, budget - committed)
    alert_th = _num(profile.get("alertThreshold")) or 75
    urgent_th = _num(profile.get("urgentThreshold")) or 85

    # 1) Puntuación base
    sub = c.get("subscores") or {}
    breakdown, raw, evidenced = [], 0.0, 0
    for key, label, weight in CRITERIA:
        s = sub.get(key) or {}
        v = _num(s.get("v"))
        v = 0.0 if v is None else max(0.0, min(10.0, v))
        ev = bool(s.get("evidence"))
        capped = False
        if not ev and v > NO_EVIDENCE_MAX:
            v, capped = float(NO_EVIDENCE_MAX), True
        evidenced += ev
        pts = weight * v / 10
        raw += pts
        breakdown.append({"key": key, "label": label, "weight": weight, "value": v,
                          "points": round(pts, 1), "why": s.get("why", ""), "evidence": ev,
                          "cappedForNoEvidence": capped})

    # 2) Banderas (declaradas por el agente + calculadas)
    flags = [dict(f) for f in (c.get("redFlags") or [])]
    flags += market_flags(c.get("market") or {})
    reg = c.get("regulatory") or {}
    if reg.get("status") in CRITICAL_REG:
        flags.append({"code": "regulatorio", "severity": "critica",
                      "detail": reg.get("notes") or "Entidad con advertencia o sin autorización de la CNMV/ESMA."})
    # deduplicar por código
    seen, uniq = set(), []
    for f in flags:
        if f.get("code") in seen:
            continue
        seen.add(f.get("code"))
        uniq.append(f)
    flags = uniq

    # 3) Penalizaciones y topes
    caps = []
    score = raw
    altas = [f for f in flags if f.get("severity") == "alta"]
    if altas:
        pen = min(20, 5 * len(altas))
        score -= pen
        caps.append(f"-{pen} por {len(altas)} riesgo(s) alto(s)")
    criticals = [f for f in flags if f.get("severity") == "critica"]
    if criticals:
        if score > 20:
            caps.append("Tope 20: riesgo crítico (" + ", ".join(f["code"] for f in criticals) + ")")
        score = min(score, 20)
    min_entry = _num((c.get("costs") or {}).get("minEntry"))
    if min_entry is not None and min_entry > budget:
        if score > 39:
            caps.append(f"Tope 39: la entrada mínima ({min_entry:.0f} €) supera tu presupuesto")
        score = min(score, 39)
    if c.get("spainAvailability") == "no":
        if score > 39:
            caps.append("Tope 39: no disponible para residentes en España")
        score = min(score, 39)
    if evidenced < MIN_EVIDENCED:
        if score > 59:
            caps.append(f"Tope 59: solo {evidenced}/12 criterios con evidencia")
        score = min(score, 59)
    score = int(round(max(0.0, min(100.0, score))))

    tier_key, tier_label = next((k, l) for th, k, l in TIERS if score >= th)

    # 4) Nivel de riesgo (no se oculta tras la puntuación)
    liquidity = c.get("liquidity", "desconocida")
    can_lose_all = bool(c.get("canLoseAll", True))
    if criticals:
        risk = "crítico"
    elif can_lose_all and (len(altas) >= 2 or liquidity in ("baja", "nula")):
        risk = "muy alto"
    elif can_lose_all:
        risk = "alto"
    elif altas:
        risk = "medio"
    else:
        risk = "bajo" if c.get("kind") == "activa" else "medio"

    # 5) Escenarios
    costs = c.get("costs") or {}
    stake = _num(costs.get("recommended")) or min_entry or 0.0
    stake = min(stake, available if available > 0 else budget, budget)
    scen = scenarios(c, stake, fx)

    # 6) Momentum / detección temprana
    m = c.get("market") or {}
    snap = {"t": now}
    for k in ("priceUsd", "liquidityUsd", "volume24hUsd", "fdvUsd", "holders"):
        if _num(m.get(k)) is not None:
            snap[k] = _num(m.get(k))
    for k, v in (c.get("signals") or {}).items():
        if _num(v) is not None:
            snap[k] = _num(v)
    history = list((existing or {}).get("metrics") or [])
    mom = momentum(snap, history)
    if mom["label"] == "Retirada de liquidez" and not any(f["code"] == "retirada_liquidez" for f in flags):
        flags.append({"code": "retirada_liquidez", "severity": "critica",
                      "detail": "La liquidez ha caído más de un 50% desde la última comprobación (posible rug pull)."})
        criticals.append(flags[-1])
        risk = "crítico"
        if score > 20:
            caps.append("Tope 20: retirada de liquidez")
            score = 20
            tier_key, tier_label = next((k, l) for th, k, l in TIERS if score >= th)
    metrics = (history + [snap])[-30:] if len(snap) > 1 else history

    # 7) Decisión de alerta (deduplicada)
    is_new = existing is None
    action = (existing or {}).get("userAction")  # guardada | descartada | investigada | None
    prev_score = _num((existing or {}).get("score"))
    notified = bool((existing or {}).get("notifiedAt"))
    deadline = c.get("deadline")
    hours_left = None
    if deadline:
        try:
            dl = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            hours_left = (dl - datetime.fromisoformat(now.replace("Z", "+00:00"))).total_seconds() / 3600
        except ValueError:
            hours_left = None

    level, reason = "ninguna", ""
    if action == "descartada":
        level, reason = "ninguna", "Descartada por ti"
    elif not is_new and criticals and action in ("guardada", "investigada") and not (existing or {}).get("critical"):
        level, reason = "urgente", "Riesgo crítico nuevo en una oportunidad que sigues"
    elif criticals:
        level, reason = "ninguna", "Riesgo crítico: no se notifica como oportunidad"
    elif is_new or not notified:
        if score >= urgent_th and (score >= 90 or (hours_left is not None and 0 < hours_left <= 72)):
            level, reason = "urgente", "Puntuación muy alta" + (" y plazo de menos de 72 h" if hours_left and hours_left <= 72 else "")
        elif score >= alert_th:
            level, reason = "normal", "Nueva oportunidad por encima de tu umbral"
    else:
        if prev_score is not None and score - prev_score >= 10 and score >= alert_th:
            level, reason = "cambio", f"La puntuación sube de {int(prev_score)} a {score}"
        elif action in ("guardada", "investigada") and mom["label"] in ("Crecimiento acelerado",):
            level, reason = "cambio", "Crecimiento acelerado en una oportunidad que sigues"

    result = {
        "id": fingerprint(c),
        "isNew": is_new,
        "score": score,
        "rawScore": round(raw, 1),
        "tier": tier_key,
        "tierLabel": tier_label,
        "humanReview": score >= 90,
        "caps": caps,
        "critical": bool(criticals),
        "risk": risk,
        "flags": flags,
        "evidenced": evidenced,
        "breakdown": breakdown,
        "scenarios": scen,
        "momentum": mom,
        "metrics": metrics,
        "alert": {"level": level, "reason": reason},
        "hoursLeft": round(hours_left, 1) if hours_left is not None else None,
    }
    result["alertText"] = alert_text(c, result, now)
    return result


def _eur(x):
    x = _num(x)
    return "desconocido" if x is None else f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def alert_text(c: dict, r: dict, now: str) -> str:
    costs = c.get("costs") or {}
    srcs = c.get("sources") or []
    flags = r["flags"]
    distrust = [f["detail"] for f in flags] + list(c.get("distrust") or [])
    lines = [
        f"NOMBRE: {c.get('name', '')}",
        f"CATEGORÍA: {c.get('category', '')} · {c.get('subcategory', '')}",
        f"FECHA DE DESCUBRIMIENTO: {c.get('discoveredAt') or now[:10]}",
        f"WEB OFICIAL: {c.get('officialUrl') or 'no verificada'}",
        f"ENLACE DE PARTICIPACIÓN: {c.get('participateUrl') or 'no disponible'}",
        f"PAÍS: {c.get('country') or 'desconocido'}",
        f"DISPONIBILIDAD EN ESPAÑA: {c.get('spainAvailability', 'desconocida')}",
        f"COSTE DE ENTRADA: {_eur(costs.get('minEntry'))} (+ {_eur(costs.get('extra'))} adicionales)",
        f"PRESUPUESTO RECOMENDADO: {_eur(r['scenarios']['stakeEur'])}",
        f"POTENCIAL: {c.get('potential') or 'ver escenarios (simulación)'}",
        f"PUNTUACIÓN: {r['score']}/100 · {r['tierLabel']}",
        f"RIESGO: {r['risk']}",
        f"PLAZO: {c.get('horizon') or 'desconocido'}",
        "MOTIVO POR EL QUE PUEDE SER INTERESANTE: " + "; ".join(c.get("whyInteresting") or ["—"]),
        "MOTIVOS PARA DESCONFIAR: " + ("; ".join(distrust) if distrust else "ninguno detectado (eso no significa que no existan)"),
        "CÓMO PARTICIPAR: " + "; ".join(c.get("howToParticipate") or ["—"]),
        "QUÉ PODRÍA HACERME PERDER EL DINERO: " + "; ".join(c.get("lossCauses") or ["—"]),
        "FUENTES: " + " | ".join(s.get("url", "") for s in srcs[:6]),
    ]
    return "\n".join(lines)


def run(payload: dict) -> dict:
    profile = payload.get("profile") or {}
    now = payload.get("now") or datetime.now(timezone.utc).isoformat()
    fx = _num((payload.get("fx") or {}).get("usdToEur"))
    existing = payload.get("existing") or {}
    out, errors = [], []
    for i, c in enumerate(payload.get("candidates") or []):
        try:
            if c.get("category") not in ALLOWED_CATEGORIES:
                raise ValueError(f"categoría no válida: {c.get('category')}")
            fid = fingerprint(c)
            out.append(evaluate(c, profile, existing.get(fid), now, fx))
        except Exception as e:  # una candidata mal formada no detiene la ejecución
            errors.append({"index": i, "name": c.get("name"), "error": str(e)})
    out.sort(key=lambda r: r["score"], reverse=True)
    return {"now": now, "results": out, "errors": errors,
            "alerts": [{"id": r["id"], "level": r["alert"]["level"], "reason": r["alert"]["reason"]}
                       for r in out if r["alert"]["level"] != "ninguna"]}


if __name__ == "__main__":
    src = open(sys.argv[1], encoding="utf-8") if len(sys.argv) > 1 else sys.stdin
    print(json.dumps(run(json.load(src)), ensure_ascii=False, indent=1))
