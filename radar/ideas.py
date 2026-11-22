"""Ideas para copiar: apps, SaaS, software y negocios que han triunfado hace poco en algún país y que se podrían
replicar en España, Egipto o el Golfo Pérsico (CCG).

Cada día: recoge noticias de startups (RSS gratuitos, Hacker News, Product Hunt), una IA elige las que describen un
producto concreto con éxito demostrable, otra lo analiza a fondo leyendo el artículo y un modelo distinto comprueba
que los datos de tracción salen del texto (los que no, se eliminan). Guarda enlaces a las fuentes.
Uso: python -m radar.ideas [--data data] [--force]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import collectors, net, notify, prompts
from .llm import Router

MAX_DEEP = 8
KEEP = 80
MARKETS = {"es": "España", "eg": "Egipto", "gcc": "Golfo (EAU, Arabia Saudí, Catar, Kuwait, Baréin, Omán)"}
DEFAULT_FEEDS = [
    {"name": "TechCrunch Startups", "url": "https://techcrunch.com/category/startups/feed/"},
    {"name": "TechCrunch Venture", "url": "https://techcrunch.com/category/venture/feed/"},
    {"name": "Crunchbase News", "url": "https://news.crunchbase.com/feed/"},
    {"name": "EU-Startups", "url": "https://www.eu-startups.com/feed/"},
    {"name": "Tech.eu", "url": "https://tech.eu/feed/"},
    {"name": "Sifted", "url": "https://sifted.eu/feed"},
    {"name": "YourStory", "url": "https://yourstory.com/feed"},
    {"name": "TechCabal", "url": "https://techcabal.com/feed/"},
    {"name": "Disrupt Africa", "url": "https://disrupt-africa.com/feed/"},
    {"name": "Wamda", "url": "https://www.wamda.com/feed"},
    {"name": "Rest of World", "url": "https://restofworld.org/feed/latest/"},
    {"name": "Product Hunt", "url": "https://www.producthunt.com/feed"},
]

SYSTEM = """Eres un analista de negocio que busca modelos probados en otros países para replicarlos en España, Egipto o el Golfo Pérsico.
Reglas: los datos de tracción (financiación, ingresos, usuarios, crecimiento) solo pueden salir del texto que te paso; no inventes cifras,
nombres, enlaces ni competidores. Si algo no consta, dilo y márcalo para verificar. Sé concreto y prudente. Responde solo con JSON válido."""

TRIAGE = """Noticias recientes de startups (número. título — resumen — fuente):
{items}

Elige como máximo {n} que describan un PRODUCTO o NEGOCIO concreto (app, SaaS, software, marketplace, e-commerce, servicio)
con señales de éxito reciente en su país (ronda de financiación, ingresos, usuarios, crecimiento rápido, adquisición) y que una
persona o equipo pequeño podría replicar en España, Egipto o el Golfo. Descarta: grandes tecnológicas, cripto/tokens, biotecnología,
hardware o deep tech que exija mucho capital, fondos de inversión, noticias generales y productos ya presentes en esos mercados.
Devuelve: {{"picks": [{{"i": número, "why": "por qué se puede copiar, en una frase"}}]}}"""

DEEP = """Fuente: {title}
URL: {url}
TEXTO DEL ARTÍCULO (puede estar incompleto):
{text}

Analiza la idea para replicarla en España (es), Egipto (eg) y el Golfo (gcc). Presupuesto de referencia del usuario: {budget} €.
Devuelve exactamente:
{{"name": "nombre del producto o empresa", "type": "app|saas|software|marketplace|ecommerce|servicio|negocio_local",
"originCountry": "país", "summary": "qué es y a quién sirve, 2 frases",
"traction": ["datos concretos de éxito tal como aparecen en el texto"],
"whyItWorked": ["razones del éxito"],
"markets": {{"es": {{"fit": 0-10, "why": "por qué encaja o no", "adapt": "qué adaptar (idioma, pagos, regulación, canal)", "competition": "competidores locales que conozcas o «no consta, verificar»"}},
            "eg": {{"fit": 0-10, "why": "...", "adapt": "...", "competition": "..."}}, "gcc": {{"fit": 0-10, "why": "...", "adapt": "...", "competition": "..."}}}},
"mvp": {{"costEur": [mínimo, máximo], "weeks": número, "team": "perfiles necesarios", "stack": "tecnología o herramientas no-code", "noCode": true|false}},
"monetization": "cómo gana dinero", "risks": ["riesgos principales"], "firstSteps": ["primeros pasos concretos para validarla"],
"officialUrl": "web oficial si aparece en el texto, si no null"}}"""

CHECK = """TEXTO:
{text}

DATOS QUE DICE EL ANÁLISIS:
{facts}

¿Cuáles de estos datos aparecen realmente en el texto (aunque con otras palabras)?
Devuelve: {{"supported": [números de los datos que sí aparecen], "notes": "observación breve"}}"""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())[:40]


def gather(cfg: dict) -> tuple[list[dict], dict]:
    feeds = [{**f, "category": "negocio"} for f in cfg.get("ideas_feeds", DEFAULT_FEEDS)]
    items, status = collectors.rss(feeds, per_feed=8)
    hn, st = collectors.hacker_news(limit=10)
    status["Hacker News"] = st
    items += hn
    seen, out = set(), []
    for it in items:
        k = it.get("url") or it.get("title")
        if k and k not in seen and it.get("title"):
            seen.add(k)
            out.append(it)
    return out, status


def score(idea: dict, budget: float) -> int:
    fits = [float((idea.get("markets") or {}).get(m, {}).get("fit") or 0) for m in MARKETS]
    best = max(fits) if fits else 0
    ev = min(len(idea.get("traction") or []), 3) / 3
    cost = (idea.get("mvp") or {}).get("costEur") or [None]
    lo = cost[0] if isinstance(cost, list) and cost and isinstance(cost[0], (int, float)) else None
    cs = 0.5 if lo is None else 1.0 if lo <= budget else 0.6 if lo <= 5 * budget else 0.3
    return round(40 * best / 10 + 25 * ev + 20 * cs + 15 * (1.0 if idea.get("verified") else 0.4))


def run(data_dir: Path, cfg: dict, force: bool = False, transport=None) -> dict:
    p = data_dir / "ideas.json"
    prev = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    t = now_utc()
    if not force and prev.get("generatedAt") and t - datetime.fromisoformat(prev["generatedAt"].replace("Z", "+00:00")) < timedelta(hours=20):
        print("Ideas: ya se actualizó hace menos de 20 h")
        return {"skipped": True}
    profile = {**cfg.get("profile", {})}
    prof_p = data_dir / "profile.json"
    if prof_p.exists():
        profile.update(json.loads(prof_p.read_text(encoding="utf-8")))
    prompts.set_context(profile)
    budget = float(profile.get("budget", 2000) or 2000)
    items, status = gather(cfg)
    seen_urls = set(prev.get("seenUrls", []))
    fresh = [it for it in items if it.get("url") not in seen_urls][:70]
    router = Router(cfg, transport=transport)
    new_ideas, errors = [], []
    if fresh:
        lines = []
        for i, it in enumerate(fresh):
            summ = re.sub(r"\s+", " ", it.get("summary") or "")[:220]
            lines.append(f"{i}. {it['title'][:140]} — {summ} — {it.get('source')}")
        listing = "\n".join(lines)
        tri = router.ask_role("analyst", prompts.loc(SYSTEM), prompts.loc(TRIAGE.format(items=listing, n=MAX_DEEP)))
        picks = [x for x in ((tri or {}).get("data") or {}).get("picks", []) if isinstance(x, dict)][:MAX_DEEP]
        known = {_norm(i.get("name")) for i in prev.get("items", [])}
        for pk in picks:
            try:
                it = fresh[int(pk.get("i"))]
            except (ValueError, TypeError, IndexError):
                continue
            text = net.page_text(it["url"], 7000) or ""
            if len(text) < 300 or text.startswith("["):
                text = f"{it['title']}. {it.get('summary') or ''}"
            res = router.ask_role("analyst", prompts.loc(SYSTEM), prompts.loc(DEEP.format(title=it["title"], url=it["url"], text=text, budget=int(budget))))
            d = (res or {}).get("data")
            if not isinstance(d, dict) or not d.get("name") or _norm(d["name"]) in known:
                continue
            facts = [str(x) for x in (d.get("traction") or [])][:6]
            d["verified"] = False
            if facts:
                chk = router.ask_role("verifier", prompts.loc(SYSTEM), CHECK.format(
                    text=text[:6000], facts="\n".join(f"{i}. {f}" for i, f in enumerate(facts))), exclude={res["provider"]})
                sup = ((chk or {}).get("data") or {}).get("supported")
                if isinstance(sup, list):
                    keep = [facts[i] for i in sup if isinstance(i, int) and 0 <= i < len(facts)]
                    d["droppedFacts"] = len(facts) - len(keep)
                    d["traction"] = keep
                    d["verified"] = bool(keep)
                    d["checkedBy"] = f"{chk['provider']}:{chk['model']}"
            off = d.get("officialUrl") if isinstance(d.get("officialUrl"), str) and d["officialUrl"].startswith("http") else None
            links = [{"title": f"{it.get('source')}: {it['title'][:90]}", "url": it["url"]}]
            if off and off not in text and _norm(d["name"])[:6] not in _norm(off):
                off = None  # web oficial no respaldada por el texto
            if off:
                links.append({"title": "Web oficial", "url": off})
            links.append({"title": f"Buscar «{d['name']}» en Google", "url": "https://www.google.com/search?q=" + re.sub(r"\s+", "+", d["name"])})
            d.update({"id": _norm(d["name"]) or _norm(it["url"]), "officialUrl": off, "links": links, "source": it.get("source"),
                      "foundAt": iso(t), "why": pk.get("why"), "analyst": f"{res['provider']}:{res['model']}"})
            d["score"] = score(d, budget)
            known.add(_norm(d["name"]))
            new_ideas.append(d)
        errors = router.errors[-6:]
    seen_urls |= {it.get("url") for it in fresh if it.get("url")}
    all_items = new_ideas + prev.get("items", [])
    all_items.sort(key=lambda x: (x.get("foundAt", "")[:10], x.get("score", 0)), reverse=True)
    out = {"generatedAt": iso(t), "items": all_items[:KEEP], "status": status, "aiErrors": errors,
           "seenUrls": list(seen_urls)[-600:], "newCount": len(new_ideas), "studied": len(fresh)}
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    app = os.environ.get("APP_URL", "")
    for d in sorted(new_ideas, key=lambda x: -x["score"])[:2]:
        if d["score"] >= 75:
            best = max(MARKETS, key=lambda m: float((d.get("markets") or {}).get(m, {}).get("fit") or 0))
            notify.send(f"💡 Idea para copiar: {d['name']}", f"{d.get('summary', '')[:180]} Mejor encaje: {MARKETS[best].split(' (')[0]} "
                        f"(nota {d['score']}/100).", priority=3, tags=["bulb"], click=(app + "#ideas") if app else None)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    out = run(Path(a.data), cfg, a.force)
    if not out.get("skipped"):
        print(json.dumps({"nuevas": out["newCount"], "estudiadas": out["studied"], "errores": out["aiErrors"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
