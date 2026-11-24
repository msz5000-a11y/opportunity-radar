import json, requests
UA = {"User-Agent": "Mozilla/5.0 OpportunityRadarAI/3.0", "Origin": "https://msz5000-a11y.github.io"}
r = requests.get("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=.SPX%7C.IXIC%7CUS10Y%7C%40LCO.1%7C%40GC.1%7C%40SI.1&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1", headers=UA, timeout=20)
d = r.json()
for q in d["FormattedQuoteResult"]["FormattedQuote"]:
    print("###", json.dumps({k: q.get(k) for k in ("symbol", "name", "shortName", "last", "change", "change_pct", "previous_day_closing", "last_time", "curmktstatus", "changetype", "realTime")}))
print("### keys", sorted(d["FormattedQuoteResult"]["FormattedQuote"][0].keys()))
