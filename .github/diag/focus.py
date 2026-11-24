"""Prueba real de las novedades «Desde casa»: qué devuelve cada búsqueda, qué pasa los filtros y qué dice la IA."""
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import quote_plus

sys.path.insert(0, ".")
from radar import pulse, pulse_sources as S  # noqa: E402
from radar.casa_rules import HL, local_queries, looks_like_case, story_queries  # noqa: E402

now = datetime.now(timezone.utc)
profs = [p for p in json.load(open("data/profiles.json"))["profiles"] if p.get("casa")]
cfg = json.load(open("config.json"))
os.makedirs("samples", exist_ok=True)
raw = []
for p in profs:
    for kind, qs in (("story", story_queries(p)), ("local", local_queries(p))):
        for lang, q in qs:
            hl = HL[lang]
            url = f"https://news.google.com/rss/search?q={quote_plus(q + ' when:30d')}&hl={hl[0]}&gl={hl[1]}&ceid={hl[2]}"
            try:
                r = S.fetch(url, timeout=20)
                rows = S.parse_feed(r.text) if r is not None else []
            except Exception as e:  # noqa: BLE001
                print("ERR", q, e)
                rows = []
            raw.append({"perfil": p["id"], "kind": kind, "q": q, "n": len(rows),
                        "titulos": [(x["title"][:160], (x.get("date") or "")[:16], looks_like_case(x["title"])) for x in rows[:12]]})
            print(f"### {kind} {lang} n={len(rows)} pasan={sum(1 for x in rows[:10] if looks_like_case(x['title']))} | {q}")
json.dump(raw, open("samples/casa_raw.json", "w"), ensure_ascii=False, indent=1)

c = S.Ctx(now, {}, {"profile": {"region": "es"}})
c.profiles = profs
jobs = sum(len(story_queries(p)) + len(local_queries(p)) for p in profs)
got = {}
for _ in range(0, jobs, S.CASA_PER_RUN):
    for it in S.c_casa(c):
        got[it["id"]] = it
items = sorted(got.values(), key=lambda x: -x["s"])
print("\n=== pasan el filtro:", len(items), "de", jobs, "búsquedas")
for it in items:
    print(it["kind"], it["s"], (it.get("pub") or "")[:10], it["src"][:20], "|", it["title"][:140])
info = {"calls": 0}
for _ in range(4):
    st = {}
    i2 = pulse.triage_casa(items, profs, st, cfg, now)
    info["calls"] += i2["calls"]
    if not i2["calls"]:
        break
print("\n=== IA:", info, )
for it in items:
    print("OK " if not it.get("h") else "NO ", it.get("tema"), "|", (it.get("es") or "")[:120], "||", (it.get("why") or "")[:150])
json.dump(items, open("samples/casa_items.json", "w"), ensure_ascii=False, indent=1)
