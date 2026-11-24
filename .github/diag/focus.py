"""Guarda muestras de páginas en la rama diag-samples para escribir los lectores sin acceso directo."""
import json, os, requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36", "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}
os.makedirs("samples", exist_ok=True)
pages = {
    "startupxplore_inversores.html": "https://startupxplore.com/es/inversores",
    "startupxplore_invertir.html": "https://startupxplore.com/es/inversores/invertir-startups",
    "dozen_home.html": "https://dozeninvestments.com/",
    "dozen_oportunidades.html": "https://dozeninvestments.com/oportunidades-de-inversion/",
    "capitalcell_home.html": "https://capitalcell.net/",
    "capitalcell_es.html": "https://capitalcell.net/es/",
    "bolsasocial.html": "https://www.bolsasocial.com/proyectos",
    "segoventure.html": "https://www.segoventure.com/proyectos",
    "adventurees.html": "https://www.adventurees.com/",
    "trustmrr.html": "https://trustmrr.com/",
    "yc_fall2026.json": "https://yc-oss.github.io/api/batches/fall-2026.json",
    "yc_winter2027.json": "https://yc-oss.github.io/api/batches/winter-2027.json",
    "producthunt.xml": "https://www.producthunt.com/feed",
}
log = {}
for name, url in pages.items():
    try:
        r = requests.get(url, headers=UA, timeout=30)
        open(f"samples/{name}", "w", encoding="utf-8").write(r.text)
        log[name] = {"status": r.status_code, "len": len(r.text), "url": url}
    except Exception as e:
        log[name] = {"error": str(e)[:200], "url": url}
json.dump(log, open("samples/log.json", "w"), indent=1)
print("### " + json.dumps(log))
