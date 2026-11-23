"""Diagnóstico puntual: BDNS, anuncios de exchanges en inglés y Groq con JSON."""
import os, json, requests
UA = {"User-Agent": "OpportunityRadarAI/3.0", "Accept-Language": "en-US,en;q=0.9"}
for q in ["emprendedores", "startups", "digitalización", "creación de empresas"]:
    r = requests.get("https://www.infosubvenciones.es/bdnstrans/api/convocatorias/busqueda", headers=UA, timeout=30,
                     params={"vpd": "GE", "page": 0, "pageSize": 8, "order": "fechaRecepcion", "direccion": "desc", "descripcion": q})
    d = r.json()
    print("### BDNS", q, r.status_code, d.get("totalElements"))
    for x in d.get("content", [])[:8]:
        print("   ", x.get("fechaRecepcion"), x.get("nivel1"), "|", (x.get("nivel2") or "")[:25], "|", (x.get("descripcion") or "")[:110])
r = requests.get("https://www.okx.com/api/v5/support/announcements", params={"annType": "announcements-new-listings"}, headers={**UA, "locale": "en-US"}, timeout=20)
print("### OKX", [x["title"] for b in r.json().get("data", []) for x in b.get("details", [])][:8])
r = requests.get("https://www.binance.com/bapi/composite/v1/public/cms/article/list/query", params={"type": 1, "catalogId": 48, "pageNo": 1, "pageSize": 10}, headers=UA, timeout=20)
print("### BINANCE", [a["title"] for c in r.json()["data"]["catalogs"] for a in c.get("articles", [])][:10])
k = os.environ.get("GROQ_API_KEY")
body = {"model": "openai/gpt-oss-20b", "temperature": 0.2, "max_completion_tokens": 2600, "reasoning_effort": "low",
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": "Devuelve JSON {\"items\":[{\"i\":0,\"t\":\"titular en español\"}]}"},
                     {"role": "user", "content": json.dumps([{"i": 0, "titular": "Binance will list FooCoin (FOO)"}, {"i": 1, "titular": "Fed holds rates"}])}]}
r = requests.post("https://api.groq.com/openai/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {k}"}, timeout=60)
print("### GROQ json", r.status_code, r.text[:400])
