"""Muestras para «Desde casa»: BDNS por región y municipio, historias de éxito en Google News y Starter Story."""
import json, os, requests
from urllib.parse import quote_plus
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36", "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}
os.makedirs("samples", exist_ok=True)
B = "https://www.infosubvenciones.es/bdnstrans/api"
pages = {
    "bdns_regiones.json": f"{B}/regiones?vpd=GE",
    "bdns_organos_L.json": f"{B}/organos?vpd=GE&idAdmon=L",
    "bdns_organos_A.json": f"{B}/organos?vpd=GE&idAdmon=A",
    "bdns_riba.json": f"{B}/convocatorias/busqueda?vpd=GE&page=0&pageSize=20&order=fechaRecepcion&direccion=desc&descripcion=riba-roja",
    "bdns_ribarroja.json": f"{B}/convocatorias/busqueda?vpd=GE&page=0&pageSize=20&order=fechaRecepcion&direccion=desc&descripcion=ribarroja",
    "bdns_valencia_empr.json": f"{B}/convocatorias/busqueda?vpd=GE&page=0&pageSize=20&order=fechaRecepcion&direccion=desc&descripcion=emprendimiento%20valenciana",
    "bdns_labora.json": f"{B}/convocatorias/busqueda?vpd=GE&page=0&pageSize=20&order=fechaRecepcion&direccion=desc&descripcion=labora",
    "gnews_en.xml": "https://news.google.com/rss/search?q=" + quote_plus('"from home" business success story etsy OR "side hustle" when:60d') + "&hl=en-US&gl=US&ceid=US:en",
    "gnews_es.xml": "https://news.google.com/rss/search?q=" + quote_plus('"desde casa" negocio éxito emprendedora when:60d') + "&hl=es&gl=ES&ceid=ES:es",
    "gnews_kids.xml": "https://news.google.com/rss/search?q=" + quote_plus('"from home" business kids printables OR "children\'s book" earns when:90d') + "&hl=en-US&gl=US&ceid=US:en",
    "starterstory.html": "https://www.starterstory.com/ideas",
    "starterstory_home.html": "https://www.starterstory.com/home-business-ideas",
}
log = {}
for name, url in pages.items():
    try:
        r = requests.get(url, headers=UA, timeout=40)
        open(f"samples/{name}", "w", encoding="utf-8").write(r.text)
        log[name] = {"status": r.status_code, "len": len(r.text)}
    except Exception as e:
        log[name] = {"error": str(e)[:200]}
json.dump(log, open("samples/log.json", "w"), indent=1)
print("### " + json.dumps(log))
