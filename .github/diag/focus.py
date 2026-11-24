"""Guarda muestras de páginas en la rama diag-samples para escribir los lectores sin acceso directo."""
import json, os, requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36", "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}
os.makedirs("samples", exist_ok=True)
pages = {
    "bdns_detail_938656.json": "https://www.infosubvenciones.es/bdnstrans/api/convocatorias?numConv=938656&vpd=GE",
    "bdns_search.json": "https://www.infosubvenciones.es/bdnstrans/api/convocatorias/busqueda?vpd=GE&page=0&pageSize=5&order=fechaRecepcion&direccion=desc&descripcion=emprendedores",
    "sx_deal.html": "https://startupxplore.com/es/inversores/invertir-startups/bonomicrowd2026",
    "dozen_deal.html": "https://dozeninvestments.com/oportunidades-de-inversion/my-gocu/",
    "cc_campaign.html": "https://capitalcell.com/campaign/nanogrow-biotech/",
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
