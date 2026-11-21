"""Orquestador de OPPORTUNITY RADAR AI v2.

buscar (APIs + Gemini con Google Search) → analizar (modelo A) → verificar (modelo B, distinto)
→ consenso → puntuación determinista → deduplicación → guardar → alertas push (ntfy) → resúmenes.

Uso:  python -m radar.pipeline [--mode auto|scan|digest|weekly|test-notify|check] [--data data] [--dry]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import collectors, net, notify, prompts, scoring
from .llm import Router

MADRID = ZoneInfo("Europe/Madrid")
CRIT_KEYS = [k for k, _, _ in scoring.CRITERIA]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


# ------------------------------------------------------------------ almacenamiento
class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def load(self, name, default):
        p = self.root / name
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    def save(self, name, data):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)


# ------------------------------------------------------------------ consenso entre modelos
def merge_subscores(a: dict, b: dict | None) -> tuple[dict, float | None]:
    if not b:
        return a, None
    out, agree, n = {}, 0, 0
    for k in CRIT_KEYS:
        sa, sb = (a or {}).get(k) or {}, (b or {}).get(k) or {}
        va, vb = sa.get("v"), sb.get("v")
        try:
            va = float(va) if va is not None else None
            vb = float(vb) if vb is not None else None
        except (TypeError, ValueError):
            va = vb = None
        if va is None and vb is None:
            out[k] = {"v": 0, "why": "sin datos", "evidence": False}
            continue
        if va is None or vb is None:
            v = va if vb is None else vb
            src = sa if vb is None else sb
            out[k] = {"v": v, "why": (src.get("why") or "") + " (un solo modelo)", "evidence": False}
            continue
        n += 1
        diff = abs(va - vb)
        if diff <= 2:
            agree += 1
        v = min(va, vb) if diff >= 3 else round((va + vb) / 2, 1)
        why = sa.get("why") or ""
        if sb.get("why") and sb.get("why") != why:
            why = f"{why} · Verificador: {sb.get('why')}"
        if diff >= 3:
            why += f" · Discrepancia entre modelos ({va:g} vs {vb:g}): se toma el valor bajo."
        out[k] = {"v": v, "why": why.strip(" ·"), "evidence": bool(sa.get("evidence")) and bool(sb.get("evidence")) and diff < 3}
    return out, (round(agree / n * 100) if n else None)


def apply_verification(ficha: dict, ver: dict | None, verifier_model: str | None) -> dict:
    f = dict(ficha)
    flags = list(f.get("redFlags") or [])
    if not ver:
        flags.append({"code": "sin_verificacion_independiente", "severity": "alta",
                      "detail": "Ningún segundo modelo pudo verificar esta ficha en esta ejecución."})
        f["redFlags"] = flags
        f["verification"] = {"verdict": "sin verificar", "model": None}
        return f
    subs, agreement = merge_subscores(f.get("subscores") or {}, ver.get("subscores"))
    f["subscores"] = subs
    flags += [x for x in (ver.get("redFlags") or []) if isinstance(x, dict) and x.get("code")]
    verdict = (ver.get("verdict") or "dudosa").lower()
    if verdict == "falsa":
        flags.append({"code": "verificacion_fallida", "severity": "critica", "detail": "El verificador no pudo confirmar que sea real: " + (ver.get("verdictReason") or "")})
    elif verdict == "dudosa":
        flags.append({"code": "verificacion_dudosa", "severity": "alta", "detail": "El verificador tiene dudas: " + (ver.get("verdictReason") or "")})
    f["redFlags"] = flags
    for field in ("officialUrl", "participateUrl", "deadline", "spainAvailability", "country"):
        val = (ver.get("corrections") or {}).get(field)
        if val and val not in ("null", "...", "desconocido"):
            f[field] = val
    reg = ver.get("regulatory") or {}
    if reg.get("checked"):
        f["regulatory"] = reg
    srcs = {s.get("url"): s for s in (f.get("sources") or []) if isinstance(s, dict) and s.get("url")}
    for s in ver.get("sources") or []:
        if isinstance(s, dict) and s.get("url", "").startswith("http"):
            srcs.setdefault(s["url"], s)
    f["sources"] = list(srcs.values())[:15]
    f["verification"] = {"verdict": verdict, "reason": ver.get("verdictReason"), "model": verifier_model, "agreementPct": agreement}
    return f


# ------------------------------------------------------------------ pasos
def discover(router: Router, cfg: dict, state: dict, today: str, known: list[str]) -> list[dict]:
    cats = [c for c in cfg["profile"]["categories"] if c in cfg["discovery_queries"]]
    pool = [(c, q) for c in cats for q in cfg["discovery_queries"][c]]
    if not pool:
        return []
    cursor = state.get("discoveryCursor", 0)
    picks = [pool[(cursor + i) % len(pool)] for i in range(min(2, len(pool)))]
    state["discoveryCursor"] = (cursor + 2) % len(pool)
    out = []
    for cat, q in picks:
        res = router.ask_role("searcher", prompts.DISCOVERY_SYSTEM,
                              prompts.DISCOVERY_PROMPT.format(today=today, query=q, category=cat, known=", ".join(known[-60:]) or "ninguna"),
                              search=True, require_search=True)
        if not res:
            continue
        grounding = [{"title": g["title"], "url": router.resolve_redirect(g["url"])} for g in res["grounding"][:6]]
        for c in (res["data"] or {}).get("candidates", [])[:4]:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            out.append({"source": f"Búsqueda IA ({res['model']})", "category": cat, "kind": "descubrimiento",
                        "title": c["name"], "url": c.get("officialUrl") or (c.get("sourceUrls") or [None])[0],
                        "summary": f"{c.get('summary', '')} {c.get('whyNow', '')}".strip(),
                        "participateUrl": c.get("participateUrl"), "deadline": c.get("deadline"),
                        "extraSources": [u for u in c.get("sourceUrls") or [] if isinstance(u, str) and u.startswith("http")],
                        "grounding": grounding, "searchModel": res["model"]})
    return out


def analyse(router: Router, cfg: dict, item: dict, today: str, available: float, previous: dict | None) -> dict | None:
    market_block = "no aplica"
    if item.get("market"):
        flags, extra = collectors.token_security(item["market"].get("chain"), item["market"].get("tokenAddress") or "")
        item["market"].update({k: v for k, v in extra.items() if k in ("top10Pct", "holders")})
        item["securityFlags"], item["securityChecks"] = flags, extra.get("checks", [])
        market_block = json.dumps({"market": item["market"], "securityFlags": flags}, ensure_ascii=False)
    page = net.page_text(item.get("url") or "", cfg["limits"]["page_text_chars"]) if item.get("url") else ""
    raw = {k: item.get(k) for k in ("source", "title", "url", "summary", "participateUrl", "deadline", "signals", "extraSources", "category")}
    res = router.ask_role("analyst", prompts.ANALYST_SYSTEM,
                          prompts.ANALYST_PROMPT.format(today=today, available=round(available, 2),
                                                        raw=json.dumps(raw, ensure_ascii=False),
                                                        market=market_block, page=page or "(sin texto)",
                                                        previous=json.dumps(_compact(previous), ensure_ascii=False) if previous else "ninguna"))
    if not res or not isinstance(res["data"], dict):
        return None
    ficha = res["data"]
    ficha["category"] = ficha.get("category") if ficha.get("category") in scoring.ALLOWED_CATEGORIES else item.get("category", "negocio")
    if item.get("market"):
        ficha["market"] = {k: v for k, v in item["market"].items() if k not in ("websites", "socials")}
        ficha["redFlags"] = list(ficha.get("redFlags") or []) + item.get("securityFlags", [])
        ficha["securityChecks"] = item.get("securityChecks", [])
    srcs = [{"title": item.get("source", "fuente"), "url": item["url"]}] if item.get("url") else []
    srcs += [{"title": "Fuente", "url": u} for u in item.get("extraSources") or []]
    srcs += item.get("grounding") or []
    if item.get("market", {}).get("pairUrl"):
        srcs.append({"title": "Par en DEX", "url": item["market"]["pairUrl"]})
    ficha["sources"] = srcs
    sig = dict(item.get("signals") or {})
    sig.update({k: v for k, v in (ficha.get("signals") or {}).items() if isinstance(v, (int, float))})
    ficha["signals"] = sig
    ficha["discoveredVia"] = item.get("source")
    ficha["aiModels"] = {"searcher": item.get("searchModel"), "analyst": f"{res['provider']}:{res['model']}"}
    raw_for_verifier = json.dumps(raw, ensure_ascii=False)
    ver = router.ask_role("verifier", prompts.VERIFIER_SYSTEM,
                          prompts.VERIFIER_PROMPT.format(today=today, ficha=json.dumps(_compact(ficha), ensure_ascii=False), raw=raw_for_verifier,
                                                         page=(page or "(sin texto)")[:4000]),
                          search=True, exclude={res["provider"]})
    ficha = apply_verification(ficha, ver["data"] if ver and isinstance(ver["data"], dict) else None,
                               f"{ver['provider']}:{ver['model']}" if ver else None)
    if ver:
        ficha["aiModels"]["verifier"] = f"{ver['provider']}:{ver['model']}"
        for g in ver.get("grounding") or []:
            ficha["sources"].append({"title": g["title"], "url": router.resolve_redirect(g["url"])})
    ficha["discoveredAt"] = today
    ficha["sources"] = clean_sources(ficha.get("sources"))
    return ficha


def clean_sources(srcs) -> list[dict]:
    from urllib.parse import urlparse
    out, seen = [], set()
    for s in srcs or []:
        if not isinstance(s, dict) or not str(s.get("url", "")).startswith("http") or s["url"] in seen:
            continue
        seen.add(s["url"])
        title = s.get("title") or ""
        if title.lower() in ("", "fuente", "src", "source") or title.startswith("Búsqueda IA"):
            title = urlparse(s["url"]).netloc.removeprefix("www.")
        out.append({"title": title[:120], "url": s["url"]})
    return out[:15]


def _compact(d: dict | None) -> dict | None:
    if not d:
        return d
    drop = {"metrics", "scenarios", "breakdown", "alertText", "momentum"}
    return {k: v for k, v in d.items() if k not in drop}


def refresh_token(doc: dict) -> dict | None:
    """Re-comprobación barata (sin IA) de un token ya conocido: mercado + seguridad."""
    m = doc.get("market") or {}
    if not m.get("tokenAddress"):
        return None
    data = net.get_json(f"{collectors.DEX}/latest/dex/tokens/{m['tokenAddress']}")
    pairs = data.get("pairs") or []
    if not pairs:
        new_m = dict(m, liquidityUsd=0, volume24hUsd=0)
    else:
        best = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
        new_m = {k: v for k, v in collectors._pair_to_market(best).items() if k not in ("websites", "socials")}
    flags, extra = collectors.token_security(new_m.get("chain"), new_m.get("tokenAddress") or "")
    new_m.update({k: v for k, v in extra.items() if k in ("top10Pct", "holders")})
    cand = {k: v for k, v in doc.items() if k in scoring_input_keys()}
    cand["market"] = new_m
    keep = [f for f in (doc.get("redFlags") or []) if not str(f.get("code", "")).startswith(("rugcheck_", "honeypot", "control_propietario", "mint", "impuesto_venta"))]
    cand["redFlags"] = keep + flags
    return cand


def probe_id(it: dict) -> str:
    """Huella del elemento bruto (antes del análisis) para no re-analizar lo mismo."""
    if it.get("kind") == "noticia" and it.get("url"):
        return scoring.slugify("news-" + it["url"].split("://", 1)[-1], 90)
    return scoring.fingerprint({"name": it.get("title"), "officialUrl": it.get("url"), "market": it.get("market")})


def scoring_input_keys():
    return {"name", "category", "subcategory", "kind", "description", "officialUrl", "participateUrl", "country",
            "spainAvailability", "spainNotes", "costs", "canLoseAll", "liquidity", "exitNotes", "horizon", "deadline",
            "potential", "difficulty", "timeNeeded", "subscores", "redFlags", "distrust", "whyInteresting",
            "howToParticipate", "lossCauses", "earlySignals", "market", "signals", "regulatory", "sources",
            "discoveredAt", "aiModels", "verification", "securityChecks", "discoveredVia"}


# ------------------------------------------------------------------ resúmenes
def build_digest(kind: str, opps: dict, runs: list, profile: dict, actions_note: str = "") -> str:
    now = now_utc()
    span = timedelta(days=1 if kind == "diaria" else 7)
    recent = [o for o in opps.values() if o.get("lastSeenAt") and datetime.fromisoformat(o["lastSeenAt"].replace("Z", "+00:00")) > now - span]
    new = [o for o in recent if o.get("firstSeenAt") and datetime.fromisoformat(o["firstSeenAt"].replace("Z", "+00:00")) > now - span]
    rr = [r for r in runs if datetime.fromisoformat(r["startedAt"].replace("Z", "+00:00")) > now - span]
    alerts = sum(r.get("alertsSent", 0) for r in rr)
    ok_runs = sum(1 for r in rr if r.get("status") == "ok")
    top = sorted([o for o in recent if not o.get("critical")], key=lambda o: o.get("score", 0), reverse=True)[:5 if kind == "diaria" else 7]
    crit = [o for o in recent if o.get("critical")]
    lines = [f"{'📊 Resumen diario' if kind == 'diaria' else '🗓️ Resumen semanal'} · Opportunity Radar",
             f"Exploraciones: {len(rr)} ({ok_runs} sin errores) · Analizadas: {len(recent)} · Nuevas: {len(new)} · Alertas: {alerts}"]
    expected = 8 if kind == "diaria" else 56
    if len(rr) < expected * 0.6:
        lines.append(f"⚠️ Radar con incidencias: {len(rr)} de ~{expected} exploraciones previstas.")
    lines.append("")
    lines.append("Mejores sin riesgo crítico:" if top else "Sin oportunidades destacables en el periodo.")
    for o in top:
        cost = (o.get("costs") or {}).get("minEntry")
        why = (o.get("whyInteresting") or ["—"])[0]
        bad = ((o.get("flags") or [{}])[0].get("detail") if o.get("flags") else None) or (o.get("distrust") or ["sin señales concretas"])[0]
        lines.append(f"• {o.get('name')} · {o.get('score')}/100 · {o.get('category')} · entrada {cost if cost is not None else '?'} € · riesgo {o.get('risk')}")
        lines.append(f"  + {why}")
        lines.append(f"  − {bad}")
    if crit:
        lines.append("")
        lines.append("Riesgos críticos detectados: " + "; ".join(f"{o.get('name')} ({(o.get('flags') or [{}])[0].get('code', '')})" for o in crit[:6]))
    lines.append("")
    lines.append(f"Presupuesto configurado: {profile.get('budget', 150)} €. Escenarios = simulaciones. La decisión es siempre tuya.")
    return "\n".join(lines)


# ------------------------------------------------------------------ ejecución
def run(mode: str, data_dir: Path, dry: bool = False, transport=None) -> dict:
    cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))
    store = Store(data_dir)
    state = store.load("state.json", {})
    opps: dict = {o["id"]: o for o in store.load("opps.json", [])}
    runs: list = store.load("runs.json", [])
    digests: list = store.load("digests.json", [])
    status = store.load("status.json", {})
    profile = {**cfg["profile"], **{k: v for k, v in store.load("profile.json", {}).items() if k in cfg["profile"]}}
    if float(profile.get("budget", 150)) > 150 and not profile.get("budgetAuthorizedAbove150"):
        profile["budget"] = 150
    for oid, act in (store.load("actions.json", {}) or {}).items():
        if oid in opps and isinstance(act, dict):
            opps[oid]["userAction"] = act.get("action")
    router = Router(cfg, transport=transport)
    start = now_utc()
    local = start.astimezone(MADRID)
    today = local.date().isoformat()
    run_id = "run-" + start.strftime("%Y%m%d-%H%M")
    log = {"id": run_id, "startedAt": iso(start), "kind": "exploracion", "status": "ok", "candidates": 0,
           "newCount": 0, "updatedCount": 0, "alertsSent": 0, "notes": "", "sources": {}}
    notes = []

    if mode == "check":
        return {"providers": {p: bool(os.environ.get(k)) for p, k in __import__("radar.llm", fromlist=["KEYS"]).KEYS.items()},
                "ntfy": bool(os.environ.get("NTFY_TOPIC"))}
    if mode == "test-notify":
        ok = notify.send("✅ Opportunity Radar conectado", "Las alertas llegarán aquí aunque el móvil esté bloqueado.", priority=3, tags=["white_check_mark"])
        if not dry:
            store.save("notify.json", {"at": iso(now_utc()), **notify.LAST})
        return {"sent": ok, **notify.LAST}

    try:
        if mode in ("auto", "scan"):
            available = max(0.0, float(profile.get("budget", 150)))
            if not profile.get("budgetAuthorizedAbove150"):
                available = min(available, 150.0)
            items, srcs = [], {}
            fx, st = collectors.fx_usd_eur()
            srcs["tipo_cambio_BCE"] = st
            if fx:
                state["usdToEur"] = fx
            for fn in (collectors.dexscreener_tokens, collectors.geckoterminal_trending, collectors.coingecko_trending,
                       collectors.hacker_news, collectors.github_rising):
                if fn in (collectors.dexscreener_tokens, collectors.geckoterminal_trending, collectors.coingecko_trending) and "cripto" not in profile["categories"]:
                    continue
                got, st = fn()
                items += got
                srcs[fn.__name__] = st
            got, st = collectors.rss([f for f in cfg.get("rss_feeds", []) if f["category"] in profile["categories"]])
            items += got
            srcs.update(st)
            known_names = [o.get("name", "") for o in opps.values()]
            disc = discover(router, cfg, state, today, known_names)
            if not os.environ.get("GEMINI_API_KEY"):
                srcs["busqueda_ia"] = collectors._status(False, 0, "falta la clave de Gemini")
            else:
                srcs["busqueda_ia"] = collectors._status(bool(disc), len(disc), None if disc else "sin resultados: " + "; ".join(router.errors[-2:]))
            items = disc + items
            # deduplicar por huella y por nombre; ignorar descartadas por el usuario
            alias = {a: oid for oid, o in opps.items() for a in (o.get("aliases") or [])}
            seen, queue = set(), []
            for it in items:
                fid = probe_id(it)
                if fid in seen:
                    continue
                seen.add(fid)
                prev = opps.get(fid) or opps.get(alias.get(fid, ""))
                if prev and prev.get("userAction") == "descartada":
                    continue
                if prev and prev.get("lastSeenAt") and datetime.fromisoformat(prev["lastSeenAt"].replace("Z", "+00:00")) > start - timedelta(hours=20):
                    continue  # analizada hace poco: no gastar IA
                queue.append((fid, it))
            # prioridad: descubrimientos de IA y tokens con datos, luego el resto
            queue.sort(key=lambda x: (x[1]["kind"] != "descubrimiento", x[1]["kind"] != "token"))
            queue = queue[: cfg["limits"]["max_candidates_per_run"]]
            candidates = []
            for fid, it in queue:
                try:
                    prev = opps.get(fid) or opps.get(alias.get(fid, ""))
                    f = analyse(router, cfg, it, today, available, prev)
                    if f:
                        f["_probe"] = fid
                        candidates.append(f)
                except Exception as e:
                    notes.append(f"{it.get('title')}: {str(e)[:120]}")
            # re-comprobaciones baratas de tokens seguidos o bien puntuados
            rechecks = sorted([o for o in opps.values() if o.get("market") and (o.get("userAction") in ("guardada", "investigada") or o.get("score", 0) >= 60)],
                              key=lambda o: o.get("lastSeenAt", ""))[: cfg["limits"]["max_rechecks_per_run"]]
            for o in rechecks:
                try:
                    c = refresh_token(o)
                    if c:
                        candidates.append(c)
                except Exception as e:
                    notes.append(f"recheck {o.get('name')}: {str(e)[:100]}")
            existing = {k: {"score": v.get("score"), "notifiedAt": v.get("notifiedAt"), "userAction": v.get("userAction"),
                            "metrics": v.get("metrics"), "critical": v.get("critical")} for k, v in opps.items()}
            scored = scoring.run({"profile": profile, "now": iso(start), "fx": {"usdToEur": state.get("usdToEur")},
                                  "candidates": candidates, "existing": existing})
            notes += [f"error de puntuación: {e['name']}: {e['error']}" for e in scored["errors"]]
            by_id = {}
            for c in candidates:
                by_id[scoring.fingerprint(c)] = c
            alerts = []
            for r in scored["results"]:
                c = by_id.get(r["id"], {})
                prev = opps.get(r["id"], {})
                doc = {**prev, **c, **r, "firstSeenAt": prev.get("firstSeenAt") or iso(start), "lastSeenAt": iso(start), "runId": run_id}
                doc["aliases"] = sorted(set((prev.get("aliases") or []) + ([c.pop("_probe")] if c.get("_probe") else [])))
                doc.pop("_probe", None)
                if r["alert"]["level"] != "ninguna":
                    doc["lastAlert"] = {"level": r["alert"]["level"], "reason": r["alert"]["reason"], "at": iso(start)}
                    doc["notifiedAt"] = iso(start)
                    alerts.append(doc)
                if r["isNew"]:
                    log["newCount"] += 1
                else:
                    log["updatedCount"] += 1
                opps[r["id"]] = doc
            log["candidates"] = len(candidates)
            # poda
            cutoff = start - timedelta(days=cfg["limits"]["prune_discard_days"])
            for k in [k for k, o in opps.items() if o.get("tier") == "descartar" and not o.get("userAction")
                      and datetime.fromisoformat(o["lastSeenAt"].replace("Z", "+00:00")) < cutoff]:
                del opps[k]
            # alertas
            app = os.environ.get("APP_URL", "")
            for a in sorted(alerts, key=lambda d: (d["lastAlert"]["level"] != "urgente", -d.get("score", 0)))[:5]:
                lvl = a["lastAlert"]["level"]
                title = {"urgente": "🚨 URGENTE", "normal": "📡 Nueva oportunidad", "cambio": "🔁 Cambio importante"}[lvl] + f" · {a['name']} · {a['score']}/100"
                if not dry and notify.send(title, a["alertText"], priority={"urgente": 5, "normal": 4, "cambio": 3}[lvl],
                                           tags=["rotating_light" if lvl == "urgente" else "satellite"], click=f"{app}#{a['id']}" if app else None):
                    log["alertsSent"] += 1
            log["sources"] = srcs
            failing = [n for n, s in srcs.items() if not s.get("ok")]
            if failing:
                notes.append("Fuentes con fallos: " + ", ".join(failing))
            if not router.first_available("analyst"):
                notes.append("Sin modelos de IA configurados: solo se recogen datos de mercado.")
            log["status"] = "ok" if not failing and not router.errors else "parcial"

        # resúmenes
        if mode in ("auto", "digest") and (mode == "digest" or (19 <= local.hour <= 22 and state.get("lastDaily") != today)):
            text = build_digest("diaria", opps, runs + [log], profile)
            digests.insert(0, {"id": "daily-" + today, "type": "diaria", "at": iso(start), "text": text})
            state["lastDaily"] = today
            if not dry:
                notify.send("📊 Resumen diario · Opportunity Radar", text, priority=2, tags=["bar_chart"], click=os.environ.get("APP_URL") or None)
        if mode in ("auto", "weekly") and (mode == "weekly" or (local.weekday() == 6 and 19 <= local.hour <= 22 and state.get("lastWeekly") != today)):
            text = build_digest("semanal", opps, runs + [log], profile)
            digests.insert(0, {"id": "weekly-" + today, "type": "semanal", "at": iso(start), "text": text})
            state["lastWeekly"] = today
            store.save(f"backups/week-{today}.json", [{k: o.get(k) for k in ("id", "name", "category", "score", "tier", "risk", "critical", "officialUrl", "participateUrl", "firstSeenAt", "lastSeenAt")} for o in opps.values()])
            if not dry:
                notify.send("🗓️ Resumen semanal · Opportunity Radar", text, priority=2, tags=["calendar"], click=os.environ.get("APP_URL") or None)
    except Exception as e:
        log["status"] = "error"
        notes.append("Fallo general: " + str(e)[:300])
        traceback.print_exc()

    # supervisión: avisar si fallan varias ejecuciones seguidas
    recent_status = [r.get("status") for r in runs[:2]] + [log["status"]]
    if recent_status.count("error") >= 3 and not dry:
        notify.send("⚠️ Opportunity Radar con incidencias", "Las 3 últimas ejecuciones han fallado. Revisa la pestaña Actions del repositorio.", priority=3, tags=["warning"])

    log["finishedAt"] = iso(now_utc())
    log["ai"] = router.usage()
    log["notes"] = " · ".join(notes)[:900]
    runs.insert(0, log)
    runs = runs[: cfg["limits"]["keep_runs"]]
    status = {"lastRunAt": log["finishedAt"], "lastRunOk": log["status"] == "ok", "lastRunId": run_id,
              "sources": {**status.get("sources", {}), **log["sources"]}, "ai": log["ai"],
              "schedule": "Cada 3 horas en GitHub Actions · resumen diario por la tarde · semanal los domingos",
              "profile": profile, "version": 2}
    store.save("opps.json", sorted(opps.values(), key=lambda o: -o.get("score", 0)))
    store.save("runs.json", runs)
    store.save("digests.json", digests[:60])
    store.save("status.json", status)
    store.save("state.json", state)
    return log


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="auto", choices=["auto", "scan", "digest", "weekly", "test-notify", "check"])
    ap.add_argument("--data", default="data")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    out = run(a.mode, Path(a.data), a.dry)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
    return 0 if (not isinstance(out, dict) or out.get("status") != "error") else 1


if __name__ == "__main__":
    sys.exit(main())
