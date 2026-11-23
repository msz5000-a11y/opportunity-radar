"""Reglas del pulso: categoría, tipo de oportunidad, puntuación, ruido y textos (es/en) sin IA.

Todo es determinista y barato: se ejecuta cada 5 minutos sobre cientos de titulares. La IA (si hay cupo)
solo afina los mejores después.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

CATS = ("cripto", "bolsa", "startups", "ia", "lanzamientos", "negocio")

# ------------------------------------------------------------------ texto
_STOP = set("""a al algo ante con contra de del desde el ella en entre era es esta este esto ha han hay la las le lo los mas más
me mi muy no nos o os para pero por que qué se ser si sí sin sobre su sus te tu un una unos y ya the of to and in for on with at by
from as is are be its it this that new after over into amid says say said will can could may more than up down out how why what
who your you our their his her has have had was were not but about vs via""".split())


def clean(text: str | None) -> str:
    t = unescape(re.sub(r"(?s)<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", t).strip()


def fold(text: str) -> str:
    """minúsculas sin tildes, para buscar palabras clave en es/en a la vez."""
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9$][a-z0-9$.+\-]{1,}", fold(text))
    return {w.strip(".-") for w in words if len(w.strip(".-")) >= 3 and w not in _STOP}


def similar(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter < 3:
        return 0.0
    return inter / len(a | b)


def h(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def canon_url(url: str | None) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "ref", "src", "fbclid", "gclid", "mc_", "guccounter"))]
    host = p.netloc.lower().removeprefix("www.")
    return urlunparse((p.scheme or "https", host, p.path.rstrip("/"), "", urlencode(q), ""))


# ------------------------------------------------------------------ palabras clave
def _kw(*words):
    return [fold(w).strip() for w in words if w.strip()]


def _pat(w: str) -> str:
    p = re.escape(w)
    if w[:1].isalnum():
        p = r"(?<![a-z0-9])" + p
    if w[-1:].isalnum():
        p = p + r"(?![a-z0-9])"
    return p


def _rx(words) -> re.Pattern:
    return re.compile("|".join(_pat(w) for w in sorted(set(words), key=len, reverse=True)))


CAT_WORDS = {
    "cripto": _kw("bitcoin", "btc", "ethereum", "ether", "solana", "crypto", "cripto", "criptomoneda", "criptomonedas", "token", "tokens",
                  "blockchain", "defi", "stablecoin", "stablecoins", "binance", "coinbase", "kraken", "nft", "web3", "altcoin",
                  "altcoins", "memecoin", "xrp", "dogecoin", "staking", "layer 2", "onchain", "on-chain", "wallet", "satoshi", "tether",
                  "usdc", "dex", "bitcoin etf", "ether etf", "microstrategy", "mstr", "zcash", "cardano", "polkadot", "avalanche"),
    "bolsa": _kw("stock", "stocks", "shares", "nasdaq", "s&p", "dow jones", "earnings", "wall street", "bolsa", "acciones", "ibex",
                 "dividend", "dividendo", "fed", "inflation", "inflacion", "treasury", "bond", "bonds", "bonos", "guidance", "analyst",
                 "analysts", "downgrade", "downgraded", "upgraded", "buyback", "recompra", "market cap", "merger", "acquisition",
                 "adquisicion", "opa", "takeover", "nyse", "etf", "s&p 500", "russell", "rate cut", "tipos de interes", "revenue",
                 "profit", "beneficio", "investors", "inversores", "shareholders", "accionistas", "premarket", "after-hours"),
    "startups": _kw("startup", "startups", "start-up", "raises", "funding", "series a", "series b", "series c", "seed round", "pre-seed",
                    "seed", "venture", "vc", "accelerator", "aceleradora", "incubadora", "incubator", "ronda", "financiacion",
                    "unicorn", "unicornio", "crowdfunding", "emprendedor", "emprendedores", "emprendimiento", "founders", "fundadores",
                    "founder", "y combinator", "business angel", "capital riesgo", "convocatoria", "subvencion", "ayudas", "grant", "grants"),
    "ia": _kw("artificial intelligence", "inteligencia artificial", "ai", "ia", "a.i.", "llm", "llms", "gpt", "chatgpt", "openai",
              "anthropic", "claude", "gemini", "machine learning", "deep learning", "chatbot", "agents", "agentes", "ai agent", "ai agents",
              "model", "models", "modelo", "generative", "generativa", "copilot", "neural", "gpu", "gpus", "hugging face", "diffusion",
              "robot", "robots", "robotics", "deepseek", "mistral", "llama", "nvidia"),
    "lanzamientos": _kw("launch", "launches", "launched", "lanza", "lanzamiento", "ipo", "salida a bolsa", "listing", "will list",
                        "tge", "token generation event", "presale", "preventa", "beta", "waitlist", "early access", "launchpool",
                        "launchpad", "testnet", "mainnet", "points program", "now available", "ya disponible", "goes live", "unveils"),
    "negocio": _kw("business model", "modelo de negocio", "side hustle", "ecommerce", "e-commerce", "franquicia", "franchise", "pymes",
                   "autonomos", "small business", "small businesses", "dropshipping", "saas", "freelance", "freelancers", "negocio",
                   "emprender", "marketplace"),
}

# intención de oportunidad: (palabras, puntos, nivel mínimo de oportunidad, etiqueta, ¿solo en el titular?)
INTENT = [
    (_kw("airdrop", "airdrops", "points program", "programa de puntos", "incentivized testnet", "testnet rewards", "retroactive rewards",
         "eligible wallets", "claim your tokens"), 24, 3, "airdrop", False),
    (_kw("launchpool", "launchpad", "megadrop", "hodler airdrop", "hodler airdrops"), 20, 3, "launchpool", False),
    (_kw("will list", "to list", "lists", "listing on", "listed on", "listara", "nuevo listado", "adds support for", "now live on",
         "available for trading", "trading starts", "begins trading"), 16, 2, "listado", True),
    (_kw("token generation event", "tge", "token launch", "lanzamiento del token"), 16, 2, "tge", False),
    (_kw("ipo", "ipos", "initial public offering", "salida a bolsa", "opv", "files to go public", "goes public", "estreno en bolsa",
         "prices ipo", "priced its ipo"), 14, 2, "ipo", True),
    (_kw("beats estimates", "tops estimates", "beat estimates", "beats expectations", "raises guidance", "raised guidance", "raises outlook",
         "supera previsiones", "supera las previsiones", "record revenue", "ingresos record"), 14, 2, "resultados", True),
    (_kw("to acquire", "acquires", "acquisition", "agrees to buy", "deal to buy", "in talks to buy", "to be acquired", "merger", "takeover",
         "buyout", "buyout premium", "adquirira", "adquiere", "adquisicion", "fusion", "opa sobre", "lanza una opa"), 15, 2, "fusion", True),
    (_kw("buyback", "share repurchase", "recompra de acciones"), 10, 2, "recompra", True),
    (_kw("fda approval", "fda approves", "approved by the fda", "aprobacion de la fda"), 16, 2, "aprobacion", True),
    (_kw("stock split", "split de acciones"), 8, 2, "split", True),
    (_kw("upgraded to buy", "upgrades to buy", "upgraded to outperform", "upgraded to overweight", "price target raised", "raises price target",
         "eleva el precio objetivo"), 8, 2, "mejora_analistas", True),
    (_kw("etf approval", "etf approved", "spot etf", "aprueba el etf"), 14, 2, "etf", True),
    (_kw("raises", "raised", "secures", "levanta", "cierra una ronda", "ronda de financiacion", "series a", "series b", "seed round",
         "pre-seed"), 9, 2, "ronda", True),
    (_kw("convocatoria", "applications open", "apply now", "call for applications", "call for startups", "inscripciones abiertas",
         "plazo de solicitud", "programa de aceleracion", "accelerator program", "open call", "abre la convocatoria"), 22, 3, "convocatoria", False),
    (_kw("subvencion", "subvenciones", "ayudas para", "ayudas a", "grant program", "grants for", "kit digital", "fondos next generation"),
     20, 3, "ayuda", False),
    (_kw("crowdfunding", "crowdcube", "fellow funders", "kickstarter", "equity crowdfunding", "micromecenazgo"), 14, 2, "crowdfunding", False),
    (_kw("hackathon", "bug bounty", "prize pool", "competition with prizes", "concurso de startups", "will pay you", "te paga"), 15, 3, "premios", False),
    (_kw("free credits", "creditos gratis", "startup program", "credits for startups", "free tier", "gratis para"), 16, 3, "creditos", False),
    (_kw("open source", "open-source", "open weights", "codigo abierto", "launches", "lanza", "unveils", "introduces", "rolls out",
         "now available", "ya disponible", "presenta"), 6, 2, "lanzamiento", True),
    (_kw("staking rewards", "yield farming", "apy"), 6, 2, "rendimiento", False),
    (_kw("short squeeze", "unusual options", "insider buying", "compras de directivos"), 10, 2, "flujo", True),
]
_INTENT_RX = [(_rx(ws), p, lvl, tag, head_only) for ws, p, lvl, tag, head_only in INTENT]
CRYPTO_CTX = _rx(_kw("crypto", "cripto", "token", "tokens", "wallet", "wallets", "blockchain", "defi", "onchain", "points", "eligible",
                     "claim", "testnet", "mainnet", "protocol", "protocolo", "web3", "dao", "solana", "ethereum", "bitcoin", "layer"))
RISK_WORDS = [
    (_kw("hack", "hacked", "hackeo", "hackean", "exploit", "exploited", "drained", "rug pull", "stolen", "robados", "phishing attack"), "alerta"),
    (_kw("sec sues", "sec charges", "lawsuit", "sues", "demanda", "investigation", "investigacion", "fined", "multa", "banned", "prohibe"), "regulacion"),
    (_kw("plunge", "plunges", "crash", "crashes", "desploma", "se hunde", "selloff", "sell-off", "liquidations", "liquidaciones", "tumble", "tumbles"), "caida"),
    (_kw("soars", "surges", "jumps", "rallies", "spikes", "pops", "se dispara", "sube con fuerza", "record high", "maximo historico", "all-time high"), "subida"),
]
_RISK_RX = [(_rx(ws), tag) for ws, tag in RISK_WORDS]
NOISE = _kw("price prediction", "prediccion de precio", "could hit", "could reach", "will reach", "to buy now", "coins to buy", "stocks to buy",
            "best crypto", "mejores criptomonedas", "top 5", "top 10", "sponsored", "patrocinado", "press release", "podcast", "newsletter",
            "weekly recap", "week in review", "roundup", "what to know", "explained", "explicado", "how to", "como invertir", "opinion",
            "op-ed", "quiz", "horoscope", "deal of the day", "black friday", "cyber monday", "ofertas", "oferta", "chollo", "chollos",
            "descuento", "descuentos", "rebajas", "next 100x", "1000x", "should you buy", "is it too late", "here's why", "here is why",
            "motley fool", "price analysis", "analisis de precio", "technical analysis", "live updates", "en directo", "review:", "hands-on",
            "probamos", "the best", "los mejores", "las mejores", "deals", "coupon", "cupon", "sorteo", "giveaway", "obituary", "dies at")
_NOISE_RX = _rx(NOISE)
MACRO = _kw("fed", "federal reserve", "inflation", "inflacion", "cpi", "jobs report", "payrolls", "gdp", "pib", "rate cut", "rate hike", "bce",
            "ecb", "tipos de interes", "treasury yields", "recession", "recesion", "tariff", "tariffs", "aranceles")
_MACRO_RX = _rx(MACRO)
_CAT_RX = {c: _rx(ws) for c, ws in CAT_WORDS.items()}
_PN_STOP = {"the", "a", "an", "how", "why", "what", "this", "that", "here", "is", "are", "will", "new", "el", "la", "los", "las", "un", "una",
            "por", "para", "con", "como", "que", "its", "it", "in", "on", "for", "to", "of", "and", "us", "eu", "uk", "ai", "ceo", "inc", "corp",
            "stock", "stocks", "shares", "bitcoin", "crypto", "market", "markets", "breaking", "update", "exclusive", "report", "says"}


def proper_nouns(title: str) -> set[str]:
    words = re.findall(r"\b[A-Z][A-Za-z0-9&\-]{2,}", title or "")
    return {fold(w) for w in words if fold(w) not in _PN_STOP}


SOURCE_TIER = {  # credibilidad / utilidad media de la fuente (0-1)
    "CoinDesk": .9, "The Block": .9, "Blockworks": .85, "Decrypt": .8, "Cointelegraph": .7, "CryptoSlate": .65, "The Defiant": .8,
    "Bitcoin Magazine": .65, "DL News": .85, "Kraken": .95, "Binance": .95, "OKX": .85, "Coinbase": .95,
    "CNBC": .9, "MarketWatch": .85, "Seeking Alpha": .75, "Benzinga": .7, "Investing.com": .7, "Expansión": .85, "Finnhub": .8,
    "TechCrunch": .9, "Crunchbase News": .85, "Sifted": .85, "El Referente": .85, "EU-Startups": .8, "Wamda": .8, "TechCabal": .75,
    "The Verge": .8, "Ars Technica": .8, "MIT Technology Review": .85, "Google AI": .85, "OpenAI": .9, "Hugging Face": .8,
    "Xataka": .7, "Product Hunt": .45, "Hacker News": .6, "Google News": .7, "BDNS": 1.0, "Bluesky": .45, "Mastodon": .4,
}


def tier(source: str) -> float:
    for k, v in SOURCE_TIER.items():
        if source.startswith(k):
            return v
    return .6


# ------------------------------------------------------------------ clasificación de noticias
def classify(title: str, summary: str, default_cat: str) -> dict:
    head = f" {fold(title)} "
    text = f"{head} {fold(summary)[:600]} "
    hits = {c: len(rx.findall(text)) + 2 * len(rx.findall(head)) for c, rx in _CAT_RX.items()}
    cat = default_cat if default_cat in CATS else "bolsa"
    best = max(hits, key=lambda c: hits[c])
    if hits[best] >= 3 and hits[best] > hits.get(cat, 0) + 1:
        cat = best
    also = [c for c, n in hits.items() if c != cat and n >= 3]
    tags, opp, pts = [], 1, 0.0
    for rx, p, level, tag, head_only in _INTENT_RX:
        in_head = bool(rx.search(head))
        if not in_head and (head_only or not rx.search(text)):
            continue
        if tag == "airdrop" and not CRYPTO_CTX.search(text.replace("airdrop", "")):
            continue  # AirDrop de Apple, etc.
        tags.append(tag)
        pts += p if in_head else p * 0.5
        opp = max(opp, level)
    risk_tags = [tag for rx, tag in _RISK_RX if rx.search(head)]
    noise = bool(_NOISE_RX.search(head)) or bool(_NOISE_RX.search(fold(summary)[:200]) and opp < 3)
    macro = bool(_MACRO_RX.search(head))
    if {"airdrop", "launchpool", "listado", "tge", "ipo"} & set(tags) and cat != "lanzamientos":
        also = [cat] + [c for c in also if c != cat]
        cat = "lanzamientos"
    if {"convocatoria", "ayuda", "crowdfunding"} & set(tags) and cat not in ("startups", "negocio"):
        also = [cat] + also
        cat = "startups"
    return {"cat": cat, "also": [c for c in dict.fromkeys(also) if c != cat][:2], "tags": tags + risk_tags + (["macro"] if macro else []),
            "opp": 0 if noise else opp, "intent": pts, "noise": noise}


def score_news(source: str, cls: dict, age_h: float | None, n_sources: int = 1) -> int:
    base = 22 + 26 * tier(source)
    s = base + min(cls["intent"], 34)
    if "macro" in cls["tags"]:
        s += 4
    if "alerta" in cls["tags"]:
        s += 6  # los avisos de hackeos/fraudes son útiles como alerta
    s += min(24, 8 * (n_sources - 1))
    if age_h is not None:
        if age_h > 24:
            s -= 12
        elif age_h > 8:
            s -= 5
        elif age_h < 1:
            s += 3
    if cls["noise"]:
        s -= 30
    return int(max(0, min(100, round(s))))


# ------------------------------------------------------------------ señales de mercado
STABLES = {"usdt", "usdc", "dai", "fdusd", "usde", "tusd", "pyusd", "usdd", "eurc", "eurs", "usds", "usd1", "gusd", "frax", "lusd",
           "susd", "busd", "usdp", "rlusd", "usdx", "eure", "usdtb", "susde", "buidl", "usyc", "bfusd", "usdf", "usdg"}
WRAPPED = {"wbtc", "weth", "steth", "wsteth", "cbbtc", "reth", "weeth", "ezeth", "cbeth", "wbeth", "meth", "lbtc", "solvbtc", "jitosol",
           "msol", "bnsol", "rseth", "tbtc", "wbnb", "clbtc", "fbtc", "jlp", "bbsol", "stkaave", "oseth", "pufeth", "lseth", "sweth"}


def is_plain_coin(symbol: str, name: str = "") -> bool:
    s = (symbol or "").lower()
    n = fold(name)
    if s in STABLES or s in WRAPPED:
        return False
    return not any(w in n for w in ("wrapped", "staked", "bridged", "usd coin", "stablecoin", "liquid staking", "restaked", "tokenized",
                                     "xstock", "bstocks", "tokenised", "backed ", "(ondo", "ondo tokenized"))


def move_bucket(pct: float, steps=(10, 20, 35, 60)) -> int:
    a = abs(pct)
    return sum(1 for s in steps if a >= s)


def score_move(pct: float, vol_ratio: float | None, mcap: float | None, threshold: float) -> int:
    a = abs(pct)
    s = 52 + min(22, (a - threshold) * 1.6)
    if vol_ratio:
        s += min(10, max(0, (vol_ratio - 0.05) * 60))
    if mcap:
        s += 6 if mcap >= 5e9 else 3 if mcap >= 1e9 else 0 if mcap >= 2e8 else -6
    return int(max(0, min(95, round(s))))


def fmt_eur(x: float | None, lang: str = "es") -> str:
    if x is None:
        return "?"
    a = abs(x)
    if a >= 1e9:
        v, u = x / 1e9, (" mil M€" if lang == "es" else "B €")
    elif a >= 1e6:
        v, u = x / 1e6, (" M€" if lang == "es" else "M €")
    elif a >= 1e3:
        v, u = x / 1e3, (" mil €" if lang == "es" else "K €")
    else:
        return fmt_price(x, "€", lang)
    s = f"{v:,.1f}"
    if lang == "es":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s + u


def fmt_usd(x: float | None, lang: str = "es") -> str:
    return fmt_eur(x, lang).replace("€", "$")


def fmt_price(x: float | None, cur: str = "€", lang: str = "es") -> str:
    if x is None:
        return "?"
    d = 2 if x >= 1 else 4 if x >= 0.01 else 8
    s = f"{x:,.{d}f}"
    if lang == "es":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s} {cur}"
    return f"{cur}{s}" if cur == "$" else f"{s} {cur}"


def fmt_pct(x: float | None, lang: str = "es") -> str:
    if x is None:
        return "?"
    s = f"{x:+.1f}"
    return (s.replace(".", ",") + " %") if lang == "es" else s + "%"


def log_score(x: float, lo: float, hi: float, smin: int, smax: int) -> int:
    if x <= lo:
        return smin
    if x >= hi:
        return smax
    return int(smin + (smax - smin) * (math.log(x) - math.log(lo)) / (math.log(hi) - math.log(lo)))
