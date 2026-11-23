"""Diagnóstico de fuentes desde el runner de GitHub: estado, tamaño, frescura y CORS. No imprime secretos."""
import os, re, json, time, concurrent.futures as cf
from datetime import datetime, timedelta, timezone
import requests

UA = "OpportunityRadarAI/3.0 (+https://github.com/msz5000-a11y/opportunity-radar; personal research)"
ORIGIN = "https://msz5000-a11y.github.io"
FH = os.environ.get("FINNHUB_API_KEY", "")
d0 = datetime.now(timezone.utc).date()
d7 = (d0 - timedelta(days=7)).isoformat()
d14 = (d0 + timedelta(days=14)).isoformat()

URLS = [
 # cripto / mercados
 ("cg_markets", "https://api.coingecko.com/api/v3/coins/markets?vs_currency=eur&order=market_cap_desc&per_page=250&page=1&price_change_percentage=1h,24h,7d"),
 ("cg_trending", "https://api.coingecko.com/api/v3/search/trending"),
 ("cg_simple", "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=eur&include_24hr_change=true"),
 ("fng", "https://api.alternative.me/fng/?limit=2"),
 ("coinbase_products", "https://api.exchange.coinbase.com/products"),
 ("kraken_pairs", "https://api.kraken.com/0/public/AssetPairs"),
 ("okx_instruments", "https://www.okx.com/api/v5/public/instruments?instType=SPOT"),
 ("okx_ann", "https://www.okx.com/api/v5/support/announcements?annType=announcements-new-listings"),
 ("bybit_ann", "https://api.bybit.com/v5/announcements/index?locale=en-US&type=new_crypto&limit=10"),
 ("binance_api", "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"),
 ("binance_vision", "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT"),
 ("binance_cms", "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId=48&pageNo=1&pageSize=10"),
 ("bitget_symbols", "https://api.bitget.com/api/v2/spot/public/symbols"),
 ("kucoin_symbols", "https://api.kucoin.com/api/v2/symbols"),
 ("llama_protocols", "https://api.llama.fi/protocols"),
 ("llama_raises", "https://api.llama.fi/raises"),
 ("gt_trending", "https://api.geckoterminal.com/api/v2/networks/trending_pools"),
 ("stooq", "https://stooq.com/q/l/?s=aapl.us,msft.us,^spx&f=sd2t2ohlcv&h&e=csv"),
 # finnhub (clave)
 ("fh_quote", f"https://finnhub.io/api/v1/quote?symbol=AAPL&token={FH}"),
 ("fh_news", f"https://finnhub.io/api/v1/news?category=general&token={FH}"),
 ("fh_news_crypto", f"https://finnhub.io/api/v1/news?category=crypto&token={FH}"),
 ("fh_news_merger", f"https://finnhub.io/api/v1/news?category=merger&token={FH}"),
 ("fh_ipo", f"https://finnhub.io/api/v1/calendar/ipo?from={d0}&to={d14}&token={FH}"),
 ("fh_earn", f"https://finnhub.io/api/v1/calendar/earnings?from={d0}&to={d0}&token={FH}"),
 ("fh_insider", f"https://finnhub.io/api/v1/stock/insider-transactions?symbol=AAPL&token={FH}"),
 ("fh_insider_sent", f"https://finnhub.io/api/v1/stock/insider-sentiment?symbol=AAPL&from={d7}&to={d0}&token={FH}"),
 ("fh_reco", f"https://finnhub.io/api/v1/stock/recommendation?symbol=AAPL&token={FH}"),
 ("fh_upgrade", f"https://finnhub.io/api/v1/stock/upgrade-downgrade?from={d7}&to={d0}&token={FH}"),
 ("fh_social", f"https://finnhub.io/api/v1/stock/social-sentiment?symbol=GME&token={FH}"),
 ("fh_company_news", f"https://finnhub.io/api/v1/company-news?symbol=NVDA&from={d7}&to={d0}&token={FH}"),
 # social
 ("ape_stocks", "https://apewisdom.io/api/v1.0/filter/all-stocks/page/1"),
 ("ape_crypto", "https://apewisdom.io/api/v1.0/filter/all-crypto/page/1"),
 ("reddit_json", "https://www.reddit.com/r/wallstreetbets/hot.json?limit=10"),
 ("reddit_rss", "https://www.reddit.com/r/CryptoCurrency/hot/.rss"),
 ("oldreddit_rss", "https://old.reddit.com/r/stocks/hot/.rss"),
 ("bsky_trending", "https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics"),
 ("bsky_search_public", "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=airdrop&sort=latest&limit=10"),
 ("bsky_search_api", "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=airdrop&sort=latest&limit=10"),
 ("masto_links", "https://mastodon.social/api/v1/trends/links?limit=10"),
 ("masto_tags", "https://mastodon.social/api/v1/trends/tags?limit=10"),
 ("masto_tag_crypto", "https://mastodon.social/api/v1/timelines/tag/crypto?limit=10"),
 ("stocktwits_trending", "https://api.stocktwits.com/api/2/trending/symbols.json"),
 ("stocktwits_stream", "https://api.stocktwits.com/api/2/streams/trending.json"),
 ("hn_front", "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30"),
 ("hn_show", "https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&numericFilters=points>20&hitsPerPage=20"),
 ("hf_models", "https://huggingface.co/api/models?sort=trendingScore&limit=10"),
 ("hf_spaces", "https://huggingface.co/api/spaces?sort=trendingScore&limit=10"),
 ("lobsters", "https://lobste.rs/hottest.json"),
 ("gh_trending_html", "https://github.com/trending?since=daily"),
 ("gdelt", "https://api.gdeltproject.org/api/v2/doc/doc?query=(airdrop%20OR%20%22IPO%22)&mode=artlist&maxrecords=20&format=json&timespan=1h"),
 ("gnews_en", "https://news.google.com/rss/search?q=airdrop+when:1d&hl=en-US&gl=US&ceid=US:en"),
 ("gnews_es", "https://news.google.com/rss/search?q=%22ronda+de+financiaci%C3%B3n%22+startup+when:2d&hl=es&gl=ES&ceid=ES:es"),
 ("bdns_1", "https://www.infosubvenciones.es/bdnstrans/api/convocatorias/busqueda?vpd=GE&page=0&pageSize=10&order=fechaRecepcion&direccion=desc&descripcion=emprendedores"),
 ("bdns_2", "https://www.infosubvenciones.es/bdnstrans/api/convocatorias/ultimas?vpd=GE&page=0&pageSize=10"),
 ("polymarket", "https://gamma-api.polymarket.com/markets?limit=3&active=true&closed=false&order=volume24hr&ascending=false"),
 ("raw_gh", "https://raw.githubusercontent.com/msz5000-a11y/opportunity-radar/main/config.json"),
 ("pages", "https://msz5000-a11y.github.io/opportunity-radar/data/status.json"),
]
RSS = [
 ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"), ("Cointelegraph", "https://cointelegraph.com/rss"),
 ("Cointelegraph ES", "https://es.cointelegraph.com/rss"), ("Decrypt", "https://decrypt.co/feed"),
 ("The Block", "https://www.theblock.co/rss.xml"), ("CryptoSlate", "https://cryptoslate.com/feed/"),
 ("The Defiant", "https://thedefiant.io/api/feed"), ("Bitcoin Magazine", "https://bitcoinmagazine.com/feed"),
 ("Blockworks", "https://blockworks.co/feed"), ("DL News", "https://www.dlnews.com/arc/outboundfeeds/rss/"),
 ("CNBC Top", "https://www.cnbc.com/id/100003114/device/rss/rss.html"), ("CNBC Markets", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
 ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"), ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
 ("Seeking Alpha", "https://seekingalpha.com/market_currents.xml"), ("Investing ES", "https://es.investing.com/rss/news.rss"),
 ("Expansion mercados", "https://e00-expansion.uecdn.es/rss/mercados.xml"), ("Cinco Dias", "https://cincodias.elpais.com/rss/cincodias/ultima_hora.xml"),
 ("El Economista", "https://www.eleconomista.es/rss/rss-mercados.php"), ("Benzinga", "https://www.benzinga.com/feed"),
 ("TechCrunch Startups", "https://techcrunch.com/category/startups/feed/"), ("TechCrunch Venture", "https://techcrunch.com/category/venture/feed/"),
 ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"), ("Crunchbase News", "https://news.crunchbase.com/feed/"),
 ("Sifted", "https://sifted.eu/feed"), ("El Referente", "https://www.elreferente.es/feed/"), ("Wamda", "https://www.wamda.com/feed"),
 ("TechCabal", "https://techcabal.com/feed/"), ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
 ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"), ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
 ("MIT TR", "https://www.technologyreview.com/feed/"), ("Product Hunt", "https://www.producthunt.com/feed"),
 ("Kraken blog", "https://blog.kraken.com/feed"), ("Coinbase blog", "https://www.coinbase.com/blog/rss.xml"),
 ("Hugging Face blog", "https://huggingface.co/blog/feed.xml"), ("OpenAI news", "https://openai.com/news/rss.xml"),
 ("Google AI blog", "https://blog.google/technology/ai/rss/"), ("Startupxplore", "https://startupxplore.com/es/blog/feed"),
 ("Emprendedores", "https://www.emprendedores.es/feed/"), ("Xataka", "https://www.xataka.com/feedburner.xml"),
 ("EU-Startups", "https://www.eu-startups.com/feed/"), ("Tech.eu", "https://tech.eu/feed/"),
]

def probe(name, url, rss=False):
    t = time.time()
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Origin": ORIGIN, "Accept": "*/*"}, timeout=25)
        dt = round(time.time() - t, 1)
        info = {"st": r.status_code, "kb": round(len(r.content) / 1024), "s": dt,
                "cors": r.headers.get("access-control-allow-origin"), "cache": r.headers.get("cache-control"),
                "rl": {k: v for k, v in r.headers.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"}}
        body = r.text
        if rss or "rss" in url or "xml" in url or "/feed" in url:
            items = re.findall(r"<(?:item|entry)[\s>]", body)
            dates = re.findall(r"<(?:pubDate|updated|published|dc:date)>([^<]+)<", body)
            info["items"] = len(items); info["newest"] = dates[:2]
        else:
            try:
                j = r.json()
                if isinstance(j, list): info["n"] = len(j); info["sample"] = json.dumps(j[:1])[:300]
                elif isinstance(j, dict): info["keys"] = list(j.keys())[:12]; info["sample"] = json.dumps(j)[:300]
            except Exception:
                info["head"] = body[:160].replace("\n", " ")
        return name, info
    except Exception as e:
        return name, {"err": str(e)[:160], "s": round(time.time() - t, 1)}

with cf.ThreadPoolExecutor(12) as ex:
    futs = [ex.submit(probe, n, u) for n, u in URLS] + [ex.submit(probe, n, u, True) for n, u in RSS]
    for f in cf.as_completed(futs):
        n, i = f.result()
        s = json.dumps(i, ensure_ascii=False)
        if FH: s = s.replace(FH, "***")
        print(f"### {n}: {s}")

# límites de los modelos (cabeceras de cuota), sin imprimir claves
def groq(model):
    k = os.environ.get("GROQ_API_KEY")
    if not k: return "sin clave"
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {k}"},
                      json={"model": model, "messages": [{"role": "user", "content": "di ok"}], "max_tokens": 5}, timeout=30)
    return r.status_code, {k2: v for k2, v in r.headers.items() if "ratelimit" in k2.lower()}
for m in ["llama-3.1-8b-instant", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile", "meta-llama/llama-4-scout-17b-16e-instruct"]:
    try: print("### GROQ", m, groq(m))
    except Exception as e: print("### GROQ", m, "err", str(e)[:100])
k = os.environ.get("GROQ_API_KEY")
if k:
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {k}"}, timeout=30)
        print("### GROQ models:", sorted(m["id"] for m in r.json().get("data", [])))
    except Exception as e: print("### GROQ models err", e)
g = os.environ.get("GEMINI_API_KEY")
if g:
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": g}, timeout=30)
        print("### GEMINI models:", sorted(m["name"] for m in r.json().get("models", []) if "flash" in m["name"] or "gemma" in m["name"])[:40])
    except Exception as e: print("### GEMINI models err", e)
