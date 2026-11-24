import json, requests
UA = {"User-Agent": "Mozilla/5.0 OpportunityRadarAI/3.0", "Origin": "https://msz5000-a11y.github.io"}
syms = "@GC.1|@SI.1|XAU=|XAG=|@LCO.1|US10Y"
r = requests.get("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol", params={"symbols": syms, "requestMethod": "itv", "noform": 1, "partnerId": 2, "fund": 1, "exthrs": 1, "output": "json", "events": 1}, headers=UA, timeout=20)
for q in r.json()["FormattedQuoteResult"]["FormattedQuote"]:
    print("### CNBC", json.dumps({k: v for k, v in q.items() if k not in ("EventData", "ExtendedMktQuote", "FundamentalData", "issuer_id", "issueId")}, ensure_ascii=False))
for s in ("XAU", "XAG"):
    try: print("### GOLDAPI", s, requests.get(f"https://api.gold-api.com/price/{s}", headers=UA, timeout=15).text[:300])
    except Exception as e: print("### GOLDAPI", s, "ERR", e)
for s in ("GC=F", "SI=F", "BZ=F", "^TNX"):
    try:
        m = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}", params={"range": "5d", "interval": "1d"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=15).json()["chart"]["result"][0]
        meta = m["meta"]
        print("### YAHOO", s, json.dumps({k: meta.get(k) for k in ("regularMarketPrice", "chartPreviousClose", "previousClose", "regularMarketTime", "exchangeName")}), "closes", m["indicators"]["quote"][0]["close"])
    except Exception as e: print("### YAHOO", s, "ERR", e)
