import json, re, requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36", "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}
def probe(url, n=300, js=False):
    try:
        r = requests.get(url, headers=UA, timeout=25)
        t = r.text
        print(f"### {r.status_code} {url} len={len(t)} type={r.headers.get('content-type','')[:40]}")
        if js:
            return r.json()
        m = re.findall(r'<title>(.*?)</title>', t[:5000], re.S)
        print("###   title:", (m[0].strip()[:100] if m else "-"))
        for kw in ("__NEXT_DATA__", "application/ld+json", "campaign", "ronda", "invest", "minimum", "mínimo"):
            i = t.find(kw)
            if i >= 0:
                print(f"###   [{kw}] ...{t[max(0,i-80):i+n].replace(chr(10),' ')[:n]}")
        return t
    except Exception as e:
        print("### ERR", url, e)
meta = probe("https://yc-oss.github.io/api/meta.json", js=True)
if meta:
    print("### YC meta keys:", list(meta.keys())[:20])
    b = meta.get("batches") or {}
    print("### YC batches sample:", json.dumps(b)[:600] if b else json.dumps(meta)[:800])
for u in ["https://www.crowdcube.com/explore/investment-opportunities", "https://www.fellowfunders.es/proyectos/",
          "https://startupxplore.com/es/inversores", "https://capitalcell.net/", "https://dozeninvestments.com/",
          "https://europe.republic.com/", "https://www.producthunt.com/feed", "https://trustmrr.com/"]:
    probe(u)
