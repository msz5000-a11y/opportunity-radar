"""Diagnóstico puntual: fuentes gratuitas para Brent, bono de EE. UU. a 10 años, oro y plata (y CORS)."""
import os, json, time, requests
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) OpportunityRadarAI/3.0", "Origin": "https://msz5000-a11y.github.io", "Accept": "*/*"}
FH = os.environ.get("FINNHUB_API_KEY", "")
URLS = [
 ("cnbc", "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=US10Y%7C%40LCO.1%7C%40GC.1%7C%40SI.1&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1"),
 ("yahoo_bz", "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?range=1d&interval=15m"),
 ("yahoo_tnx", "https://query2.finance.yahoo.com/v8/finance/chart/%5ETNX?range=1d&interval=15m"),
 ("yahoo_gc", "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?range=1d&interval=15m"),
 ("goldapi_xau", "https://api.gold-api.com/price/XAU"),
 ("goldapi_xag", "https://api.gold-api.com/price/XAG"),
 ("goldprice_org", "https://data-asg.goldprice.org/dbXRates/USD"),
 ("fh_oanda_xau", f"https://finnhub.io/api/v1/quote?symbol=OANDA:XAU_USD&token={FH}"),
 ("fh_oanda_bco", f"https://finnhub.io/api/v1/quote?symbol=OANDA:BCO_USD&token={FH}"),
 ("fh_forex_rates", f"https://finnhub.io/api/v1/forex/rates?base=USD&token={FH}"),
 ("fh_gld", f"https://finnhub.io/api/v1/quote?symbol=GLD&token={FH}"),
 ("fh_bno", f"https://finnhub.io/api/v1/quote?symbol=BNO&token={FH}"),
 ("fred_dgs10", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"),
 ("fred_brent", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"),
 ("stooq", "https://stooq.com/q/l/?s=cb.f,gc.f,si.f,10usy.b&f=sd2t2ohlcp&h&e=csv"),
 ("treasury", "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv"),
 ("cg_simple_usd", "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,pax-gold,tether-gold,kinesis-silver&vs_currencies=usd&include_24hr_change=true"),
 ("marketwatch_tmubmusd10y", "https://www.marketwatch.com/investing/bond/tmubmusd10y?countrycode=bx"),
 ("investing_api", "https://api.investing.com/api/financialdata/8833/historical/chart/?period=P1D&interval=PT15M&pointscount=60"),
]
for name, url in URLS:
    t = time.time()
    try:
        r = requests.get(url, headers=UA, timeout=25)
        body = r.text[:420].replace("\n", " ")
        if FH: body = body.replace(FH, "***")
        print(f"### {name}: st={r.status_code} kb={len(r.content)//1024} s={round(time.time()-t,1)} cors={r.headers.get('access-control-allow-origin')} | {body}")
    except Exception as e:
        print(f"### {name}: ERR {str(e)[:150]}")
