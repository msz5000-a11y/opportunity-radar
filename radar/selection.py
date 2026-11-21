"""Oportunidades seleccionadas y manuales de uso.

Después de cada exploración estudia TODAS las oportunidades guardadas y aplica un filtro estricto de
9 criterios. Las que pasan todos son «seleccionadas». Para las mejores candidatas pide a un modelo de
IA distinto del analista una segunda opinión (leyendo la web oficial cuando robots.txt lo permite) y
un manual práctico: cómo se gana dinero, cuánto poner, pasos, plan de salida y señales para abandonar.

Nunca ejecuta operaciones: el manual es para que la persona decida y actúe por su cuenta.
Uso: python -m radar.selection [--data data] [--dry]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import net, notify
from . import prompts
from .llm import Router

MIN_SCORE = 70
MAX_SELECTED = 5
MAX_NEAR = 3
MAX_AI_PER_RUN = 6
MANUAL_TTL_DAYS = 7
FRESH_DAYS = 14
VERIFY_FLAG = "sin_verificacion_independiente"

CRITERIA = [
    ("nota", f"Nota del radar de {MIN_SCORE}/100 o más"),
    ("verificada", "Verificada por un segundo modelo de IA independiente"),
    ("riesgos", "Sin riesgos críticos y como mucho 1 riesgo alto"),
    ("espana", "Disponible en tu región"),
    ("presupuesto", "Coste de entrada dentro de tu presupuesto"),
    ("riesgo_global", "Riesgo global medio o bajo (ni «muy alto» ni «crítico»)"),
    ("fuentes", "Web oficial y al menos 2 fuentes"),
    ("beneficio", "Vía clara y legal para ganar dinero"),
    ("vigente", "Vigente: no descartada, plazo abierto y vista hace menos de 14 días"),
]

SYSTEM = """Eres un analista prudente que ayuda a una persona residente en España a decidir si una oportunidad merece la pena sin pasar del presupuesto máximo que se indica.
Haces dos cosas: (1) una segunda opinión independiente sobre la ficha que te dan, y (2) un manual práctico para aprovecharla.
Reglas estrictas:
- Usa SOLO los datos de la ficha y el texto de la web oficial que te paso. No inventes cifras, enlaces, plazos, nombres ni resultados.
- Si un dato no está, dilo («no consta») y añade un paso para comprobarlo.
- Nunca sugieras compartir frases semilla o claves privadas, conectar la cartera a webs no oficiales, pedir préstamos, invertir más del presupuesto ni automatizar compras.
- Un proyecto de software gratuito, una noticia o un repositorio NO son una vía para ganar dinero salvo que exista un mecanismo concreto (recompensas, airdrop, venta de un servicio, afiliación, participación en una ronda, etc.).
- Sé concreto y breve. Español de España. Responde solo con JSON válido."""

PROMPT = """FICHA DEL RADAR (JSON):
{ficha}

TEXTO DE LA WEB OFICIAL (puede estar vacío o bloqueado):
{web}

Presupuesto máximo de la persona: {budget} €.

Devuelve exactamente este JSON:
{{
 "segundaOpinion": {{"veredicto": "confirmada" | "dudosa" | "rechazada", "motivo": "1-2 frases", "contradicciones": ["datos de la ficha que no cuadran con la web o entre sí"]}},
 "viaDeBeneficio": {{"existe": true | false, "explicacion": "cómo se obtiene exactamente el beneficio económico, o por qué no lo hay"}},
 "resumen": "qué es, en 2 frases sencillas",
 "cuantoPoner": "importe concreto dentro del presupuesto y por qué; 0 € si no requiere capital",
 "antesDeEmpezar": ["comprobaciones concretas antes de poner tiempo o dinero"],
 "pasos": [{{"titulo": "acción corta", "detalle": "cómo hacerlo", "tiempo": "estimación"}}],
 "planDeSalida": "cuándo y cómo recoger beneficios o cortar pérdidas",
 "senalesDeAlarma": ["señales concretas para abandonar"],
 "erroresTipicos": ["errores que hacen perder dinero"],
 "fiscalidad": "nota orientativa para un residente en España (IRPF, etc.), recomendando confirmar con un asesor",
 "tiempoNecesario": "dedicación total estimada"
}}"""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _parse(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _flags(o: dict) -> list[dict]:
    return [f for f in (o.get("flags") or o.get("redFlags") or []) if isinstance(f, dict)]


def _host(u: str | None) -> str:
    from urllib.parse import urlparse
    try:
        return urlparse(u or "").netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _analyst_model(o: dict) -> str:
    return str(((o.get("aiModels") or {}).get("analyst")) or "")


def deterministic_checks(o: dict, budget: float, now: datetime) -> dict:
    """Criterios que no necesitan IA. 'verificada' y 'beneficio' se completan después."""
    flags = _flags(o)
    crit = [f for f in flags if f.get("severity") in ("critica", "crítica", "critical")] or ([1] if o.get("critical") else [])
    high = [f for f in flags if f.get("severity") == "alta" and f.get("code") != VERIFY_FLAG]
    costs = o.get("costs") or {}
    entry = costs.get("minEntry")
    hosts = {_host(s.get("url")) for s in (o.get("sources") or []) if isinstance(s, dict) and s.get("url")}
    hosts.discard("")
    seen = _parse(o.get("lastSeenAt") or o.get("updatedAt") or o.get("discoveredAt") or o.get("firstSeenAt"))
    deadline = _parse(o.get("deadline"))
    pipeline_verified = (o.get("verification") or {}).get("verdict") not in (None, "", "sin verificar") and not any(
        f.get("code") == VERIFY_FLAG for f in flags)
    return {
        "nota": (o.get("score") or 0) >= MIN_SCORE,
        "verificada": pipeline_verified,
        "riesgos": not crit and len(high) <= 1,
        "espana": o.get("spainAvailability") == "si",
        "presupuesto": entry is not None and float(entry) <= budget,
        "riesgo_global": (o.get("risk") or "desconocido") in ("bajo", "medio"),
        "fuentes": bool(o.get("officialUrl")) and len(hosts | {_host(o.get("officialUrl"))} - {""}) >= 2,
        "beneficio": False,
        "vigente": o.get("userAction") != "descartada" and (deadline is None or deadline > now)
                   and (seen is None or now - seen < timedelta(days=FRESH_DAYS)),
    }


def _ficha(o: dict) -> dict:
    keep = ["name", "category", "subcategory", "kind", "description", "officialUrl", "participateUrl", "country",
            "spainAvailability", "spainNotes", "costs", "canLoseAll", "liquidity", "exitNotes", "horizon", "deadline",
            "potential", "difficulty", "timeNeeded", "redFlags", "distrust", "whyInteresting", "howToParticipate",
            "lossCauses", "regulatory", "sources", "score", "risk", "market", "scenarios"]
    return {k: o[k] for k in keep if k in o}


def selector_router(cfg: dict, transport=None) -> Router:
    """Router para la segunda opinión: prefiere un proveedor/modelo distinto del analista habitual."""
    c = copy.deepcopy(cfg)
    m = c.setdefault("models", {})
    prefs = m.get("groq_preference", [])
    m["groq_preference"] = prefs[1:] + prefs[:1]  # el primero es el que usa el analista
    m["selector"] = ["openrouter", "groq", "gemini"]
    lim = c.setdefault("limits", {}).setdefault("max_llm_calls", {})
    for p in ("openrouter", "groq", "gemini"):
        lim[p] = min(int(lim.get(p, 0) or 0), MAX_AI_PER_RUN + 2)
    return Router(c, transport=transport)


def second_opinion(router: Router, o: dict, budget: float, read_web: bool = True) -> dict | None:
    web = net.page_text(o.get("officialUrl"), 5000) if (read_web and o.get("officialUrl")) else ""
    prompt = PROMPT.format(ficha=json.dumps(_ficha(o), ensure_ascii=False)[:9000], web=web or "(vacío)", budget=int(budget))
    res = router.ask_role("selector", prompts.loc(SYSTEM), prompts.loc(prompt))
    if not res or not isinstance(res.get("data"), dict):
        return None
    d = res["data"]
    used = f'{res["provider"]}:{res["model"]}'
    d["modelo"] = used
    d["independiente"] = used != _analyst_model(o)
    d["webLeida"] = bool(web) and not web.startswith("[")
    d["generadoEn"] = iso(now_utc())
    d["fichaScore"] = o.get("score")
    return d


def _fresh(manual: dict | None, o: dict, now: datetime) -> bool:
    if not manual:
        return False
    at = _parse(manual.get("generadoEn"))
    return bool(at) and now - at < timedelta(days=MANUAL_TTL_DAYS) and manual.get("fichaScore") == o.get("score")


def adjusted_score(o: dict, checks: dict, manual: dict | None) -> int:
    """Devuelve los 5 puntos que el radar resta por falta de verificación si la segunda opinión la confirma."""
    s = int(o.get("score") or 0)
    flags = _flags(o)
    if manual and manual.get("independiente") and (manual.get("segundaOpinion") or {}).get("veredicto") == "confirmada" \
            and any(f.get("code") == VERIFY_FLAG for f in flags):
        s += 5
    return min(100, s)


def gemini_diagnostic() -> dict | None:
    """Una llamada mínima a Gemini para guardar el motivo real de los errores 429 (sin exponer la clave)."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    import requests
    out = {"at": iso(now_utc())}
    try:
        r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent",
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                          json={"contents": [{"parts": [{"text": "Responde solo: ok"}]}]}, timeout=30)
        out["status"] = r.status_code
        if r.status_code != 200:
            err = (r.json() or {}).get("error", {}) if "json" in r.headers.get("Content-Type", "") else {}
            out["message"] = str(err.get("message", r.text))[:500].replace(key, "***")
            out["reason"] = [d.get("reason") or d.get("@type") for d in err.get("details", []) if isinstance(d, dict)][:4]
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)[:200]
    return out


def run(data_dir: Path, cfg: dict, dry: bool = False, transport=None, read_web: bool = True) -> dict:
    now = now_utc()
    raw = _load(data_dir / "opps.json", [])
    opps = list(raw.values()) if isinstance(raw, dict) else list(raw)
    profile = {**cfg.get("profile", {}), **{k: v for k, v in _load(data_dir / "profile.json", {}).items()}}
    cap = float(cfg.get("profile", {}).get("maxBudget", 2000) or 2000)
    if not profile.get("budgetAuthorizedAbove150"):
        cap = min(cap, 150.0)
    budget = min(float(profile.get("budget", cap) or cap), cap)
    prompts.set_context(profile)
    actions = _load(data_dir / "actions.json", {}) or {}
    for o in opps:
        a = actions.get(o.get("id"))
        if isinstance(a, dict) and a.get("action"):
            o["userAction"] = a["action"]
    prev = _load(data_dir / "selected.json", {})
    manuals: dict = prev.get("manuals", {}) if isinstance(prev, dict) else {}
    prev_selected = {s["id"] for s in prev.get("selected", [])} if isinstance(prev, dict) else set()

    checks = {o["id"]: deterministic_checks(o, budget, now) for o in opps if o.get("id")}
    det_keys = ["riesgos", "espana", "presupuesto", "riesgo_global", "fuentes", "vigente"]

    def base_ok(oid):
        return all(checks[oid][k] for k in det_keys)

    # Candidatas para IA: primero las que pasan todo lo determinista (nota con margen de 5 por la verificación),
    # después las mejores de entre las que pasan lo básico, para tener manuales de las más cercanas.
    ranked = sorted([o for o in opps if o.get("id")], key=lambda o: -(o.get("score") or 0))
    strong = [o for o in ranked if base_ok(o["id"]) and (o.get("score") or 0) >= MIN_SCORE - 5]
    near = [o for o in ranked if base_ok(o["id"]) and o not in strong][:MAX_NEAR]
    router = selector_router(cfg, transport) if not dry else None
    ai_used, ai_errors = 0, []
    for o in strong + near:
        oid = o["id"]
        if _fresh(manuals.get(oid), o, now):
            continue
        if dry or ai_used >= MAX_AI_PER_RUN:
            continue
        ai_used += 1
        try:
            m = second_opinion(router, o, budget, read_web=read_web)
        except Exception as e:  # noqa: BLE001
            m = None
            ai_errors.append(f"{oid}: {str(e)[:120]}")
        if m:
            manuals[oid] = m

    results = []
    for o in ranked:
        oid = o["id"]
        c = dict(checks[oid])
        m = manuals.get(oid)
        if m:
            so = (m.get("segundaOpinion") or {}).get("veredicto")
            c["verificada"] = c["verificada"] or (bool(m.get("independiente")) and so == "confirmada")
            if so in ("dudosa", "rechazada"):
                c["verificada"] = False
            c["beneficio"] = bool((m.get("viaDeBeneficio") or {}).get("existe"))
        adj = adjusted_score(o, c, m)
        c["nota"] = adj >= MIN_SCORE
        failed = [label for k, label in CRITERIA if not c[k]]
        results.append({"id": oid, "name": o.get("name"), "category": o.get("category"), "score": o.get("score"),
                        "adjustedScore": adj, "risk": o.get("risk"), "officialUrl": o.get("officialUrl"),
                        "minEntry": (o.get("costs") or {}).get("minEntry"), "canLoseAll": o.get("canLoseAll"),
                        "checks": c, "passed": sum(1 for k, _ in CRITERIA if c[k]), "failed": failed,
                        "hasManual": oid in manuals})

    selected = [r for r in results if not r["failed"]]
    selected.sort(key=lambda r: -r["adjustedScore"])
    selected = selected[:MAX_SELECTED]
    sel_ids = {r["id"] for r in selected}
    near_list = sorted([r for r in results if r["id"] not in sel_ids and r["checks"]["vigente"]],
                       key=lambda r: (-r["passed"], -r["adjustedScore"]))[:5]
    keep_ids = sel_ids | {r["id"] for r in near_list} | {o["id"] for o in strong + near}
    manuals = {k: v for k, v in manuals.items() if k in keep_ids}

    out = {
        "generatedAt": iso(now), "minScore": MIN_SCORE, "budget": budget,
        "criteria": [{"id": k, "label": v} for k, v in CRITERIA],
        "studied": len(results), "selected": selected, "nearMisses": near_list, "manuals": manuals,
        "ai": {"used": ai_used, "errors": (ai_errors + (router.errors if router else []))[-10:],
               "calls": router.usage().get("calls") if router else {}},
    }
    diag = gemini_diagnostic() if not dry else None
    if diag:
        out["geminiDiagnostic"] = diag
    new_sel = [r for r in selected if r["id"] not in prev_selected]
    if not dry:
        (data_dir / "selected.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        app = os.environ.get("APP_URL", "")
        for r in new_sel:
            notify.send(f"⭐ Seleccionada: {r['name']}",
                        f"Ha superado los {len(CRITERIA)} criterios estrictos (nota {r['adjustedScore']}/100). "
                        f"Abre la app para ver el manual paso a paso. No es asesoramiento financiero.",
                        priority=4, tags=["star"], click=(app + "#seleccion") if app else None)
    out["newSelected"] = [r["id"] for r in new_sel]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    out = run(Path(a.data), cfg, a.dry)
    print(json.dumps({k: out[k] for k in ("generatedAt", "studied", "ai", "newSelected")}, ensure_ascii=False))
    print("Seleccionadas:", [(r["name"], r["adjustedScore"]) for r in out["selected"]])
    print("Más cercanas:", [(r["name"], r["adjustedScore"], r["failed"]) for r in out["nearMisses"]])
    if out.get("geminiDiagnostic"):
        print("Diagnóstico Gemini:", out["geminiDiagnostic"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
