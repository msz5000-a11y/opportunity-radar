import json, os, requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"}
B = "https://www.infosubvenciones.es/bdnstrans/api/convocatorias/busqueda"
base = {"vpd": "GE", "page": 0, "pageSize": 8, "order": "fechaRecepcion", "direccion": "desc"}
tests = {"region54": {"regiones": 54}, "region57": {"regiones": 57}, "organo2611": {"organos": 2611}, "organo2774": {"organos": 2774},
         "tipoL_region57": {"tipoAdministracion": "L", "regiones": 57}, "tipoA_region54": {"tipoAdministracion": "A", "regiones": 54},
         "region54_empr": {"regiones": 54, "descripcion": "emprendimiento"}, "region54_autonom": {"regiones": 54, "descripcion": "autónomos"},
         "region57_comercio": {"regiones": 57, "descripcion": "comercio"}}
for name, extra in tests.items():
    try:
        r = requests.get(B, params={**base, **extra}, headers=UA, timeout=40)
        d = r.json() if r.status_code == 200 else {}
        rows = [(x.get("numeroConvocatoria"), x.get("fechaRecepcion"), x.get("nivel1"), (x.get("nivel2") or "")[:25], (x.get("descripcion") or "")[:70]) for x in d.get("content", [])[:5]]
        print(f"### {name}: status {r.status_code} total {d.get('totalElements')} {rows}")
    except Exception as e:
        print(f"### {name}: ERR {e}")
