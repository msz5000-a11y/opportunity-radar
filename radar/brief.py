"""«Para ti»: Claude estudia todo lo que recoge el radar y elige, para cada perfil, lo poco que de verdad le sirve.

Secciones (como mucho): startups 2 · clonar 2 · accion 1 · ayudas 3 · extra 2. Si nada merece la pena, la sección
queda vacía con una nota: preferimos no recomendar nada antes que rellenar con ruido.

Fuentes que se recogen aquí (gratis, sin claves):
- Rondas abiertas en plataformas reguladas: Startupxplore, Capital Cell y Dozen (fichas con ticket mínimo).
- Negocios que funcionan para clonar: ideas del radar (ya analizadas para España y Egipto), Y Combinator (últimas
  tandas, yc-oss), TrustMRR (ingresos verificados) y Product Hunt.
- Acciones: el radar de mercados (valor + calidad + momento y la señal de ruptura).
- Ayudas: BDNS, solo convocatorias abiertas en concurrencia competitiva para personas físicas, autónomos o pymes.
- Lo mejor del pulso de las últimas 36 h.

Decide Claude (API de Anthropic, ANTHROPIC_API_KEY) con búsqueda web limitada y un tope de gasto diario. Sin clave,
o si se pasa el tope, decide el respaldo gratuito (Gemini, Groq u OpenRouter) sin búsqueda. Nunca compra ni vende:
solo analiza. Solo puede citar enlaces que vengan de los candidatos o de sus búsquedas.

Uso: python -m radar.brief [--data data] [--feed feed.json] [--perfil es] [--force] [--check-due]
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import net, notify
from .llm import Router, extract_json

MADRID = ZoneInfo("Europe/Madrid")
API = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"
# USD por millón de tokens: entrada, salida, lectura de caché, escritura de caché (5 min).
# Fuente: platform.claude.com/docs/en/about-claude/pricing (24 nov 2026). Se pueden cambiar en config.json → brief.prices.
PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20, 5.0), "claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5),
          "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125), "claude-fable-5-2": (8.0, 40.0, 0.20, 10.0)}
SEARCH_USD = 0.01  # 10 $ por cada 1.000 búsquedas
SECTIONS = {"startups": 2, "clonar": 2, "accion": 1, "ayudas": 3, "extra": 2}
BREAKOUT = ("ruptura", "media50")  # «rompiendo al alza»: máximo de 6-12 meses con volumen o recuperación de la media de 50
DEFAULTS = {"model": "claude-opus-5-5", "effort": "medium", "max_searches": 3, "max_tokens": 16000, "daily_usd_cap": 1.0,
            "times": ["07:30"]}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
      "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}
STATUS: dict = {}


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _ok(name: str, n: int = 0, err=None):
    STATUS[name] = {"ok": err is None, "n": n, "err": str(err)[:160] if err else None}


def _get(url: str, **kw) -> str:
    return net.request("GET", url, headers=UA, timeout=30, retries=2, **kw).text


def _txt(raw: str) -> str:
    """HTML → texto con «|» entre bloques (para leer fichas sin depender de las clases CSS)."""
    t = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", raw, flags=re.S)
    t = re.sub(r"<[^>]+>", "|", t)
    t = html.unescape(t)
    t = re.sub(r"(\|\s*)+", "|", t)
    return re.sub(r"\s+", " ", t)


def _num(s) -> float | None:
    """«586.552 €», «€3.250.000», «92.8%», «1.000,50» → número."""
    if s is None:
        return None
    m = re.search(r"\d[\d.,]*", str(s))
    if not m:
        return None
    v = m.group(0)
    if "," in v and "." in v:
        v = v.replace(".", "").replace(",", ".") if v.rfind(",") > v.rfind(".") else v.replace(",", "")
    elif "," in v:
        v = v.replace(",", ".") if len(v.split(",")[-1]) <= 2 else v.replace(",", "")
    elif v.count(".") >= 1 and len(v.split(".")[-1]) == 3:
        v = v.replace(".", "")
    try:
        return float(v)
    except ValueError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _cut(s, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# ------------------------------------------------------------------ startups: rondas abiertas
def startupxplore() -> list[dict]:
    raw = _get("https://startupxplore.com/es/inversores/invertir-startups")
    out, seen = [], set()
    for blk in raw.split('<div class="syndicate syndicate-opened">')[1:]:
        blk = blk[:7000]
        url = re.search(r'href="(https://startupxplore\.com/es/inversores/invertir-startups/[^"#?]+)"', blk)
        if not url or url.group(1) in seen:  # la misma ronda sale en varias pestañas
            continue
        seen.add(url.group(1))

        def grab(rx):
            m = re.search(rx, blk, re.S)
            return html.unescape(m.group(1)).strip() if m else None
        out.append({"plataforma": "Startupxplore", "empresa": grab(r'class="logo" alt="([^"]+)"'),
                    "titulo": grab(r"<h3>\s*(.*?)\s*</h3>"), "tipo": "bono" if "type-BOND" in blk else "acciones",
                    "sector": ", ".join(re.findall(r'<span class="category">([a-z0-9\-]+)</span>', blk)) or None,
                    "invertido_eur": _num(grab(r"Invertidos</span>\s*<p[^>]*>\s*([\d.,]+)")),
                    "objetivo_min_eur": _num(grab(r"Obj\. Min\.</span>\s*<p>\s*([\d.,]+)")),
                    "objetivo_max_eur": _num(grab(r"Obj\. Max\.</span>\s*<p>\s*([\d.,]+)")),
                    "inversores": _num(grab(r'<span class="number">(\d+)</span>\s*Inversores')),
                    "completado_pct": _num(grab(r'<span class="number">([\d.,]+)%</span>\s*completado')),
                    "cierre": (grab(r'data-countdown="(\d{4}/\d{2}/\d{2})"') or "").replace("/", "-") or None, "url": url.group(1)})
    for r in out[:6]:
        try:
            t = _txt(_get(r["url"]))
            r["ticket_min_eur"] = _num((re.search(r"Inversi[oó]n m[ií]nima:?\s*\|?\s*([\d.,]+)\s*(?:€|EUR)", t) or [None, None])[1])
            m = re.search(r"\|(?:Cup[oó]n|Inter[eé]s)[^|]{0,30}\|?\s*([\d.,]+\s*%)", t)
            if m:
                r["cupon"] = m.group(1)
            m = re.search(r"Pre-?money:?\s*\|?\s*([\d.,]+\s*(?:€|M€|millones)?)", t, re.I)
            if m:
                r["valoracion_premoney"] = m.group(1)
        except Exception:  # noqa: BLE001
            pass
    return out


def dozen() -> list[dict]:
    base = "https://dozeninvestments.com"
    raw = _get(base + "/oportunidades-de-inversion/")
    t = _txt(raw)
    slugs = re.findall(r'href="(/oportunidades-de-inversion/[a-z0-9\-]+/)"', raw)
    seg = t.split("Oportunidades de inversión abiertas", 1)[-1].split("Otras empresas en las que", 1)[0]
    out = []
    for chunk in seg.split("|Ver detalle|"):
        if "invertidos (" not in chunk or "Quedan" not in chunk:
            continue
        parts = [p.strip() for p in chunk.split("|") if p.strip()]
        k = next((i for i, p in enumerate(parts) if "invertidos (" in p), None)
        if k is None or k < 3:
            continue
        name, desc, target = parts[k - 3], parts[k - 2], parts[k - 1]
        slug = next((s for s in slugs if _norm(s.split("/")[-2].replace("-closed", "")) == _norm(name)), None)
        r = {"plataforma": "Dozen", "empresa": name, "titulo": desc, "tipo": None, "objetivo_eur": _num(target),
             "invertido_eur": _num(parts[k].split("invertidos")[0]), "completado_pct": _num((re.search(r"\(([\d.,]+)%\)", parts[k]) or [0, None])[1]),
             "cierre": next((p for p in parts[k + 1:k + 3] if p.startswith("Quedan")), None), "url": base + slug if slug else base + "/oportunidades-de-inversion/"}
        if slug:
            try:
                d = _txt(_get(base + slug))
                r["ticket_min_eur"] = _num((re.search(r"Ticket m[ií]nimo\|\s*([\d.,]+)\s*€", d) or [None, None])[1])
                m = re.search(r"Tipo de inversi[oó]n:\s*([^|]+)", d)
                r["tipo"] = m.group(1).strip() if m else None
                m = re.search(r"\|CAP\|\s*([\d.,]+)", d)
                if m:
                    r["cap_valoracion_eur"] = _num(m.group(1))
            except Exception:  # noqa: BLE001
                pass
        out.append(r)
    return out


def capitalcell() -> list[dict]:
    raw = _get("https://capitalcell.net/")
    t = _txt(raw)
    links = sorted(set(re.findall(r'href="(https?://capitalcell\.(?:net|com)/campaign/[a-z0-9\-]+/?)"', raw)))
    out = []
    rx = r"\|(\d+)\|d[ií]as restantes\|Objetivo\|€?\s*([\d.,]+)\s*€?\|Invertido\|([\d.,]+)%\|([^|]{2,80})\|([^|]{10,400})\|"
    for days, target, pct, name, desc in re.findall(rx, t):
        url = next((u for u in links if _norm(u.rstrip("/").split("/")[-1]) == _norm(name)), None)
        r = {"plataforma": "Capital Cell", "empresa": name.strip(), "titulo": _cut(desc, 200), "tipo": "acciones",
             "objetivo_eur": _num(target), "completado_pct": _num(pct), "cierre": f"quedan {days} días", "url": url or "https://capitalcell.net/"}
        if url:
            try:
                d = _txt(_get(url))
                r["ticket_min_eur"] = _num((re.search(r"Inversi[oó]n m[ií]nima\|\s*([\d.,]+)", d) or [None, None])[1])
                r["valoracion_premoney_eur"] = _num((re.search(r"Valoraci[oó]n Premoney\|\s*([\d.,]+)", d) or [None, None])[1])
                m = re.search(r"Equity ofrecido\s*\|\s*([\d.,]+%)", d)
                r["participacion_ofrecida"] = m.group(1) if m else None
                m = re.search(r"\|Sector\|([^|]{3,60})\|", d)
                r["sector"] = m.group(1).strip() if m else None
                m = re.search(r"Salida estimada\|(\d{4})", d)
                r["salida_estimada"] = m.group(1) if m else None
            except Exception:  # noqa: BLE001
                pass
        out.append(r)
    return out


def rounds() -> list[dict]:
    out = []
    for name, fn in (("startupxplore", startupxplore), ("capitalcell", capitalcell), ("dozen", dozen)):
        try:
            got = fn()
            _ok(name, len(got))
            out += got
        except Exception as e:  # noqa: BLE001
            _ok(name, 0, e)
    for i, r in enumerate(out):
        r["id"] = f"st{i + 1}"
    return out


# ------------------------------------------------------------------ clonar: negocios que funcionan
_SEASON = {"winter": 1, "spring": 2, "summer": 3, "fall": 4}


def yc_recent(n: int = 25) -> list[dict]:
    meta = net.get_json("https://yc-oss.github.io/api/meta.json", timeout=30) or {}
    batches = []
    for k, b in (meta.get("batches") or {}).items():
        m = re.match(r"(winter|spring|summer|fall)-(\d{4})", k)
        if m and (b.get("count") or 0) >= 15:
            batches.append((int(m.group(2)) * 10 + _SEASON[m.group(1)], b.get("api")))
    batches.sort(reverse=True)
    rows = []
    for _, api in batches[:2]:
        rows += net.get_json(api, timeout=40) or []
    keep = [c for c in rows if c.get("status") == "Active" and c.get("industry") not in ("Industrials",) and c.get("one_liner")]
    keep.sort(key=lambda c: -int(c.get("launched_at") or 0))
    out = []
    for c in keep[:n]:
        tags = c.get("tags") or []
        if isinstance(tags, str):
            tags = re.findall(r"'([^']+)'", tags)
        out.append({"fuente": "Y Combinator " + str(c.get("batch") or ""), "nombre": c.get("name"), "que_hace": _cut(c.get("one_liner"), 140),
                    "detalle": _cut(c.get("long_description"), 260), "sector": c.get("subindustry") or c.get("industry"),
                    "etiquetas": tags[:4], "equipo": c.get("team_size"), "web": c.get("website"), "url": c.get("url")})
    return out


def trustmrr(n: int = 20) -> list[dict]:
    t = _get("https://trustmrr.com/").replace('\\"', '"')
    seen, rows = set(), []
    for m in re.finditer(r'"name":"([^"]{1,80})","icon":"[^"]*","description":"([^"]{0,400})"(.{0,900}?)"slug":"([a-z0-9\-]+)"(.{0,900})', t):
        name, desc, mid, slug, tail = m.groups()
        if slug in seen or '"stealthMode":true' in mid + tail[:200]:
            continue
        seen.add(slug)
        rev = _num((re.search(r'"currentLast30DaysRevenue":([\d.]+)', mid) or [0, None])[1])
        mrr = _num((re.search(r'"currentMrr":([\d.]+)', mid) or [0, None])[1])
        tail = tail.split('"name":"', 1)[0]
        cat = (re.search(r'"userCategory":"([^"]+)"', tail) or [0, None])[1]
        growth = _num((re.search(r'"growth30d":(-?[\d.]+)', tail) or [0, None])[1])
        if "growth30d\":-" in tail:
            growth = -(growth or 0)
        price = _num((re.search(r'"askingPrice":([\d.]+)', tail) or [0, None])[1])
        if not rev or not 1500 <= rev <= 300000:
            continue
        rows.append({"fuente": "TrustMRR (ingresos verificados)", "nombre": html.unescape(name), "que_hace": _cut(html.unescape(desc), 160),
                     "ingresos_30d_usd": round(rev), "mrr_usd": round(mrr) if mrr else None, "crecimiento_30d_pct": round(growth) if growth is not None else None,
                     "categoria": cat, "en_venta_usd": round(price) if price else None, "url": f"https://trustmrr.com/startup/{slug}"})
    rows.sort(key=lambda r: -(math.log10(r["ingresos_30d_usd"]) + min(max(r["crecimiento_30d_pct"] or 0, -50), 200) / 100))
    return rows[:n]


def producthunt(n: int = 10) -> list[dict]:
    raw = _get("https://www.producthunt.com/feed")
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", raw, re.S)[:n]:
        title = html.unescape((re.search(r"<title>(.*?)</title>", e, re.S) or [0, ""])[1]).strip()
        link = (re.search(r'<link[^>]*rel="alternate"[^>]*href="([^"]+)"', e) or re.search(r'<link[^>]*href="([^"]+)"', e) or [0, ""])[1]
        content = _txt(html.unescape((re.search(r"<content[^>]*>(.*?)</content>", e, re.S) or [0, ""])[1]))
        tagline = next((p.strip() for p in content.split("|") if len(p.strip()) > 12), "")
        if title:
            out.append({"fuente": "Product Hunt", "nombre": title, "que_hace": _cut(tagline, 160), "url": link.split("?")[0]})
    return out


def ideas_prev(data_dir: Path, n: int = 14) -> list[dict]:
    p = data_dir / "ideas.json"
    if not p.exists():
        return []
    items = (json.loads(p.read_text(encoding="utf-8")) or {}).get("items") or []
    items.sort(key=lambda x: (-(x.get("score") or 0)))
    out = []
    for x in items[:n]:
        mk = x.get("markets") or {}
        links = [l.get("url") for l in (x.get("links") or []) if isinstance(l, dict) and l.get("url")]
        out.append({"fuente": "Ideas del radar", "nombre": x.get("name"), "que_hace": _cut(x.get("summary"), 220), "pais_origen": x.get("originCountry"),
                    "traccion": [_cut(t, 120) for t in (x.get("traction") or [])[:3]],
                    "encaje": {k: {"nota": (mk.get(k) or {}).get("fit"), "competencia": _cut((mk.get(k) or {}).get("competition"), 120)} for k in ("es", "eg")},
                    "mvp_eur": (x.get("mvp") or {}).get("costEur"), "regulado": x.get("regulated"),
                    "url": x.get("officialUrl") or (links[0] if links else None)})
    return out


def clone_pool(data_dir: Path) -> list[dict]:
    out = []
    for name, fn in (("ideas", lambda: ideas_prev(data_dir)), ("trustmrr", trustmrr), ("ycombinator", yc_recent), ("producthunt", producthunt)):
        try:
            got = fn()
            _ok(name, len(got))
            out += got
        except Exception as e:  # noqa: BLE001
            _ok(name, 0, e)
    for i, r in enumerate(out):
        r["id"] = f"cl{i + 1}"
    return out


# ------------------------------------------------------------------ acciones (radar de mercados)
def stock_pool(data_dir: Path, n: int = 12) -> tuple[list[dict], dict]:
    p = data_dir / "markets.json"
    if not p.exists():
        return [], {}
    m = json.loads(p.read_text(encoding="utf-8")) or {}
    st = m.get("stocks") or {}
    items = st.get("items") or []
    items = sorted(items, key=lambda x: (-(1 if (x.get("trigger") or {}).get("type") == "ruptura" and not x.get("fallingKnife") else 0),
                                         -(1 if x.get("trigger") and not x.get("fallingKnife") else 0), -(x.get("score") or 0)))
    out = []
    for x in items[:n]:
        out.append({"id": x["symbol"], "ticker": x["symbol"], "nombre": x.get("name"), "sector": x.get("sector"), "precio_usd": x.get("price"),
                    "nota_radar": x.get("score"), "senal": (x.get("trigger") or {}).get("text"), "tipo_senal": (x.get("trigger") or {}).get("type"),
                    "cuchillo_cayendo": x.get("fallingKnife"), "metricas": x.get("metrics"), "calidad": x.get("fscoreDetail"),
                    "tecnico": x.get("tech"), "valor_razonable_usd": x.get("fairValue"),
                    "url": f"https://finance.yahoo.com/quote/{x['symbol']}"})
    ctx = {"fecha_precios": st.get("priceDate"), "mercado": st.get("regime"), "estudiadas": st.get("studied"), "pasan_filtros": st.get("passed")}
    return out, ctx


# ------------------------------------------------------------------ ayudas (BDNS)
BDNS = "https://www.infosubvenciones.es/bdnstrans/api/convocatorias"
GRANT_Q = ["emprendedores", "autónomos", "pymes", "startups", "creación de empresas", "digitalización", "innovación", "jóvenes empresarios"]
GRANT_BAD = ("nominativa", "concesion directa", "subvencion directa", "a favor de", "convenio", "asociacion", "ayuntamiento de",
             "fiestas", "club", "parroquia", "camara", "federacion", "fundacion")
OK_BENEF = ("PERSONAS FÍSICAS", "PERSONAS FISICAS", "PYME")


def _fold(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


def grants(profile: dict, now: datetime, n: int = 15, days: int = 45) -> list[dict]:
    if (profile.get("country") or "").upper() != "ES":
        return []
    nums: dict[str, dict] = {}
    for q in GRANT_Q:
        try:
            d = net.get_json(BDNS + "/busqueda", params={"vpd": "GE", "page": 0, "pageSize": 25, "order": "fechaRecepcion", "direccion": "desc",
                                                         "descripcion": q}, timeout=30) or {}
        except Exception:  # noqa: BLE001
            continue
        for x in d.get("content") or []:
            num, desc = str(x.get("numeroConvocatoria") or ""), x.get("descripcion") or ""
            f = parse_iso(x.get("fechaRecepcion"))
            if not num or num in nums or any(w in _fold(desc) for w in GRANT_BAD):
                continue
            if f and (now - f.replace(tzinfo=timezone.utc)).days > days:
                continue
            nums[num] = x
    sub = _fold(profile.get("subregion") or "")
    out, today = [], now.astimezone(MADRID).date().isoformat()
    for num, x in list(nums.items())[:45]:
        try:
            det = net.get_json(BDNS, params={"numConv": num, "vpd": "GE"}, timeout=30) or {}
        except Exception:  # noqa: BLE001
            continue
        tipo = det.get("tipoConvocatoria") or ""
        benef = [b.get("descripcion", "") for b in det.get("tiposBeneficiarios") or []]
        regions = [r.get("descripcion", "") for r in det.get("regiones") or []]
        fin, ini = det.get("fechaFinSolicitud"), det.get("fechaInicioSolicitud")
        if "directa" in _fold(tipo) or not any(any(k in b.upper() for k in OK_BENEF) for b in benef):
            continue
        if fin and fin < today:
            continue
        if not fin and det.get("abierto") is False and not (ini and ini > today):
            continue
        nivel = ((det.get("organo") or {}).get("nivel1") or x.get("nivel1") or "").upper()
        national = nivel == "ESTADO" or any(r.upper().startswith("ES -") or "ESPAÑA" in r.upper() for r in regions)
        local_match = bool(sub) and any(sub in _fold(r) for r in regions + [(det.get("organo") or {}).get("nivel2") or ""])
        if nivel == "LOCAL" and not local_match:
            continue
        out.append({"id": f"gr{num}", "titulo": _cut(det.get("descripcion") or x.get("descripcion"), 220),
                    "organismo": _cut(" · ".join(v for v in ((det.get("organo") or {}).get("nivel2"), (det.get("organo") or {}).get("nivel3")) if v), 140),
                    "ambito": "estatal" if national else "autonómica" if nivel == "AUTONOMICA" else nivel.lower(),
                    "regiones": regions[:3], "tipo": tipo, "beneficiarios": benef[:3], "presupuesto_eur": det.get("presupuestoTotal"),
                    "solicitud": {"desde": ini, "hasta": fin or det.get("textFin")}, "finalidad": det.get("descripcionFinalidad"),
                    "instrumento": ", ".join(i.get("descripcion", "").strip() for i in det.get("instrumentos") or []) or None,
                    "url": f"https://www.infosubvenciones.es/bdnstrans/GE/es/convocatorias/{num}",
                    "sede": det.get("sedeElectronica"), "bases": det.get("urlBasesReguladoras"),
                    "_rank": (2 if national else 1 if local_match else 0)})
    out.sort(key=lambda g: (-g["_rank"], g["solicitud"]["hasta"] or "9999"))
    for g in out:
        g.pop("_rank", None)
    return out[:n]


# ------------------------------------------------------------------ lo mejor del pulso
def pulse_pool(feed_path: Path | None, now: datetime, n: int = 25) -> list[dict]:
    if not feed_path or not Path(feed_path).exists():
        return []
    try:
        feed = json.loads(Path(feed_path).read_text(encoding="utf-8")) or {}
    except ValueError:
        return []
    keep = []
    for it in feed.get("items") or []:
        t = parse_iso(it.get("t"))
        if not t or now - t > timedelta(hours=36) or it.get("kind") in ("grant", "context") or it.get("id", "").startswith("mc:"):
            continue
        if (it.get("opp") or 0) >= 2 and (it.get("s") or 0) >= 72:
            keep.append(it)
    keep.sort(key=lambda it: -(it.get("s") or 0))
    return [{"id": it["id"], "categoria": it.get("cat"), "tipo": it.get("kind"), "titular": _cut(it.get("es") or it.get("title"), 170),
             "por_que": _cut(it.get("why"), 200), "nota": it.get("s"), "fecha": it.get("t"), "url": it.get("url")} for it in keep[:n]]


# ------------------------------------------------------------------ Claude
RULES = """Eres el analista personal de inversiones y negocios de una persona. Tu trabajo: estudiar TODO lo que el radar ha recogido y quedarte solo con lo poco que de verdad le sirve, según su perfil. Prefiere no recomendar nada antes que rellenar con ruido: la persona se ha quejado de que recibe demasiadas cosas que no valen.

Reglas:
- Usa solo datos de los CANDIDATOS o de lo que encuentres con la búsqueda web. No inventes cifras, fechas, enlaces, nombres ni competidores. Si un dato no consta, escribe «no consta».
- Nada se compra ni se vende solo: tú analizas y la persona decide. No prometas rentabilidades. Recuerda el riesgo real (pérdida total, falta de liquidez, volatilidad).
- Ajusta cada propuesta a su capital, a su tolerancia al riesgo y a cómo puede ejecutarla de verdad.
- Como máximo: startups 2, clonar 2, accion 1, ayudas 3, extra 2. Si nada merece la pena, deja la lista vacía y explica por qué en «nota».
- startups: invertir en una startup con poco capital. Solo rondas abiertas en plataformas reguladas con ticket mínimo asumible (no más que su ticket máximo). Valora plataforma, tipo (acciones, préstamo convertible o bono), valoración, plazo, tracción y riesgo. Puedes buscar en la web si una ronda sigue abierta o rondas abiertas en otras plataformas reguladas de su país (por ejemplo Crowdcube, Fellow Funders o Bolsa Social en España). En Egipto casi no hay plataformas reguladas para particulares: dilo si es así y no propongas plataformas sin licencia.
- clonar: negocios con éxito demostrado (ingresos verificados, financiación o crecimiento) que todavía no existan o estén mal resueltos en la región del perfil. Antes de proponer uno, búscalo en la web para ver si ya hay un competidor local fuerte. Da un coste realista del producto mínimo y cómo hacerlo con sus capacidades (si no programa: socio técnico, freelance o herramientas sin código).
- accion: solo de la lista ACCIONES del radar. Prioriza señal de «ruptura» con buena nota de valor y calidad y sin «cuchillo cayendo». Ojo con las cíclicas en máximos de beneficio (navieras, petroleras, materias primas): su PER bajo puede engañar. Da zona de entrada, stop (el del radar), objetivo (el valor razonable del radar) y la relación riesgo/beneficio. Si ninguna convence, ninguna.
- ayudas: solo convocatorias abiertas en concurrencia competitiva a las que pueda optar (persona física, autónomo o pyme), con plazo y cuantía. Si no sabes su comunidad autónoma, prioriza las estatales.
- extra: como mucho 2 oportunidades del PULSO que encajen de verdad con el perfil.
- «ref» es el id del candidato (st…, cl…, el ticker, gr…, o el id del pulso). Si propones algo encontrado solo con la búsqueda web, ref = null y pon sus enlaces en «fuentes».
- Escribe en el idioma del perfil, con frases cortas y claras para leer en el móvil.

Responde SOLO con un objeto JSON, sin texto antes ni después:
{"resumen": "2-3 frases con lo más importante para esta persona",
 "secciones": {"startups": {"picks": [PICK], "nota": "..."}, "clonar": {"picks": [PICK], "nota": "..."}, "accion": {"picks": [PICK], "nota": "..."},
               "ayudas": {"picks": [PICK], "nota": "..."}, "extra": {"picks": [PICK], "nota": "..."}},
 "descartado": "una frase: qué has descartado y por qué"}
PICK = {"ref": "id o null", "titulo": "...", "resumen": "qué es, 1-2 frases", "por_que": "por qué es para esta persona", "pasos": ["qué hacer, paso a paso (máx. 4)"],
        "coste": "cuánto hace falta", "plazo": "fecha límite o «sin plazo»", "potencial": "qué se puede ganar, con prudencia", "riesgos": ["máx. 3"],
        "confianza": "alta|media|baja", "datos": {"Etiqueta corta en lenguaje normal (p. ej. «Ticket mínimo»)": "valor"}, "fuentes": ["url"]}"""


def price_of(model: str, cfg_prices: dict | None = None) -> tuple:
    p = (cfg_prices or {}).get(model) or PRICES.get(model) or PRICES["claude-opus-5-5"]
    return tuple(p)


def cost_usd(model: str, usage: dict, cfg_prices: dict | None = None) -> float:
    pin, pout, pcr, pcw = price_of(model, cfg_prices)
    st = usage.get("server_tool_use") or {}
    return round((usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout + usage.get("cache_read_input_tokens", 0) * pcr
                  + usage.get("cache_creation_input_tokens", 0) * pcw) / 1e6 + (st.get("web_search_requests", 0) or 0) * SEARCH_USD, 4)


def _urls_in(blocks: list) -> set[str]:
    out = set()
    for b in blocks or []:
        if b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
            out |= {r.get("url") for r in b["content"] if r.get("url")}
        for c in b.get("citations") or []:
            if c.get("url"):
                out.add(c["url"])
    return out


def _post(body: dict, headers: dict, transport=None) -> dict:
    """POST a la API con reintentos en 429/5xx/529 y el mensaje de error de la API si falla."""
    if transport is not None:
        return transport("POST", API, headers=headers, json=body, timeout=600, retries=2).json()
    last = None
    for attempt in range(3):
        try:
            r = net._session.post(API, headers=headers, json=body, timeout=600)
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code in (429, 500, 502, 503, 504, 529):
            last = f"HTTP {r.status_code}"
            time.sleep(min(float(r.headers.get("retry-after") or 0) or 10 * (attempt + 1), 60))
            continue
        if r.status_code >= 400:
            try:
                msg = (r.json().get("error") or {}).get("message")
            except ValueError:
                msg = r.text[:200]
            raise RuntimeError(f"HTTP {r.status_code}: {msg}")
        return r.json()
    raise RuntimeError(last or "sin respuesta")


def ask_claude(shared: str, user: str, *, model: str, effort: str, max_searches: int, max_tokens: int, transport=None) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    body = {"model": model, "max_tokens": max_tokens, "output_config": {"effort": effort},
            "system": [{"type": "text", "text": RULES}, {"type": "text", "text": shared, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}]}
    if max_searches > 0:
        body["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]
    headers = {"x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"}
    total = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "server_tool_use": {"web_search_requests": 0}}
    urls: set[str] = set()
    content: list = []
    for _ in range(4):
        d = _post(body, headers, transport)
        if d.get("type") == "error":
            raise RuntimeError((d.get("error") or {}).get("message") or "error de la API")
        u = d.get("usage") or {}
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            total[k] += u.get(k) or 0
        total["server_tool_use"]["web_search_requests"] += (u.get("server_tool_use") or {}).get("web_search_requests") or 0
        content = d.get("content") or []
        urls |= _urls_in(content)
        if d.get("stop_reason") != "pause_turn":
            break
        body["messages"] = body["messages"] + [{"role": "assistant", "content": content}]
    text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
    return {"data": extract_json(text), "usage": total, "urls": urls, "model": model, "provider": "anthropic"}


# ------------------------------------------------------------------ validación (sin datos ni enlaces inventados)
def _s(v, n: int) -> str:
    return _cut(v if isinstance(v, str) else "" if v is None else str(v), n)


def _ukey(u: str) -> str:
    u = (u or "").strip().split("#")[0].split("?")[0].rstrip("/").lower()
    return re.sub(r"^https?://(www\.)?", "", u)


def clean_brief(raw: dict, *, refs: dict[str, set], allowed_urls: set[str]) -> dict:
    """Recorta, valida referencias y enlaces. refs = {sección: ids válidos}."""
    raw = raw if isinstance(raw, dict) else {}
    allowed = {_ukey(u) for u in allowed_urls if u}
    secs = raw.get("secciones") if isinstance(raw.get("secciones"), dict) else {}
    out = {"resumen": _s(raw.get("resumen"), 500), "descartado": _s(raw.get("descartado"), 300), "secciones": {}}
    dropped = 0
    for sec, cap in SECTIONS.items():
        src = secs.get(sec) if isinstance(secs.get(sec), dict) else {}
        picks = []
        for p in (src.get("picks") or [])[: cap + 2]:
            if not isinstance(p, dict) or not _s(p.get("titulo"), 120):
                continue
            ref = p.get("ref")
            ref = str(ref).strip() if ref not in (None, "", "null") else None
            urls = [u.strip() for u in (p.get("fuentes") or []) if isinstance(u, str) and u.startswith("http") and _ukey(u) in allowed][:4]
            if ref and ref not in refs.get(sec, set()):
                ref = None
            # acciones y ayudas solo de la lista del radar; el resto, con candidato o con enlaces de su búsqueda
            if (sec in ("accion", "ayudas", "extra") and not ref) or (not ref and not urls):
                dropped += 1
                continue
            datos = p.get("datos") if isinstance(p.get("datos"), dict) else {}
            conf = _s(p.get("confianza"), 10).lower()
            picks.append({"ref": ref, "titulo": _s(p.get("titulo"), 120), "resumen": _s(p.get("resumen"), 400), "por_que": _s(p.get("por_que"), 400),
                          "pasos": [_s(x, 220) for x in (p.get("pasos") or []) if _s(x, 220)][:4],
                          "coste": _s(p.get("coste"), 100), "plazo": _s(p.get("plazo"), 80), "potencial": _s(p.get("potencial"), 200),
                          "riesgos": [_s(x, 180) for x in (p.get("riesgos") or []) if _s(x, 180)][:3],
                          "confianza": conf if conf in ("alta", "media", "baja") else "media",
                          "datos": {_s(k, 40): _s(v, 90) for k, v in list(datos.items())[:8] if _s(k, 40) and _s(v, 90)},
                          "fuentes": urls})
            if len(picks) >= cap:
                break
        out["secciones"][sec] = {"picks": picks, "nota": _s(src.get("nota"), 300)}
    out["descartados_por_validacion"] = dropped
    return out


def _money(v, cur="€") -> str | None:
    if v in (None, ""):
        return None
    try:
        return f"{float(v):,.0f}".replace(",", ".") + f" {cur}"
    except (TypeError, ValueError):
        return str(v)


def verified_facts(sec: str, c: dict, es: bool = True) -> dict:
    """Datos clave tal como vienen de la fuente (se anteponen a los que escriba el modelo)."""
    t = (lambda a, b: a if es else b)
    out: dict = {}
    if sec == "startups":
        out = {t("Plataforma", "Platform"): c.get("plataforma"), t("Ticket mínimo", "Minimum ticket"): _money(c.get("ticket_min_eur")),
               t("Tipo", "Type"): c.get("tipo"), t("Cierre", "Closes"): c.get("cierre"),
               t("Completado", "Funded"): f"{c['completado_pct']:g} %" if c.get("completado_pct") is not None else None}
    elif sec == "accion":
        tech, fv, m = c.get("tecnico") or {}, c.get("valor_razonable_usd"), c.get("metricas") or {}
        out = {t("Señal", "Signal"): c.get("senal"), t("Precio", "Price"): f"{c['precio_usd']} $" if c.get("precio_usd") is not None else None,
               "Stop": f"{tech['stop']} $" if tech.get("stop") is not None else None,
               t("Valor razonable", "Fair value"): f"{fv[0]}-{fv[1]} $" if isinstance(fv, list) and len(fv) == 2 else None,
               "PER": str(m.get("pe")) if m.get("pe") is not None else None, t("Nota del radar", "Radar score"): c.get("nota_radar")}
    elif sec == "ayudas":
        sol = c.get("solicitud") or {}
        out = {t("Plazo", "Deadline"): sol.get("hasta"), t("Presupuesto", "Budget"): _money(c.get("presupuesto_eur")),
               t("Organismo", "Body"): c.get("organismo"), t("Ámbito", "Scope"): c.get("ambito")}
    elif sec == "clonar":
        out = {t("Fuente", "Source"): c.get("fuente"), t("Ingresos 30 días", "Revenue 30 days"): _money(c.get("ingresos_30d_usd"), "$"),
               t("País de origen", "Origin"): c.get("pais_origen")}
    return {k: str(v) for k, v in out.items() if v not in (None, "", "None")}


def plain_summary(brief: dict, es: bool = True) -> str:
    """Resumen hecho con lo que de verdad quedó (para modelos gratuitos o si se descartó algo)."""
    sec = brief["secciones"]
    n = {k: len(v["picks"]) for k, v in sec.items()}
    acc = sec["accion"]["picks"][0]["titulo"] if n["accion"] else None
    if es:
        parts = [f"{n['startups']} ronda{'s' if n['startups'] != 1 else ''} abierta{'s' if n['startups'] != 1 else ''} que encaja{'n' if n['startups'] != 1 else ''} contigo" if n["startups"] else "ninguna ronda que encaje",
                 f"{n['clonar']} idea{'s' if n['clonar'] != 1 else ''} para clonar" if n["clonar"] else "ninguna idea para clonar",
                 f"acción del día: {acc}" if acc else "ninguna acción infravalorada rompe al alza"]
        if n["ayudas"]:
            parts.append(f"{n['ayudas']} ayuda{'s' if n['ayudas'] != 1 else ''} que puedes pedir")
        return "Hoy para ti: " + ", ".join(parts) + "."
    parts = [f"{n['startups']} open round{'s' if n['startups'] != 1 else ''} that fit{'s' if n['startups'] == 1 else ''} you" if n["startups"] else "no round that fits",
             f"{n['clonar']} idea{'s' if n['clonar'] != 1 else ''} to clone" if n["clonar"] else "no idea to clone",
             f"stock of the day: {acc}" if acc else "no undervalued stock breaking out"]
    return "Today for you: " + ", ".join(parts) + "."


# ------------------------------------------------------------------ orquestación
def gather(data_dir: Path, feed_path: Path | None, now: datetime) -> dict:
    st = rounds()
    cl = clone_pool(data_dir)
    stocks, sctx = stock_pool(data_dir)
    _ok("acciones", len(stocks), None if stocks else "sin markets.json")
    pl = pulse_pool(feed_path, now)
    _ok("pulso", len(pl), None if pl else "sin feed del pulso")
    return {"startups": st, "clonar": cl, "accion": stocks, "accion_ctx": sctx, "extra": pl}


def shared_block(pool: dict, now: datetime) -> str:
    local = now.astimezone(MADRID)
    j = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    return (f"FECHA: {local:%Y-%m-%d %H:%M} (hora de Madrid)\n\nCANDIDATOS recogidos hoy por el radar.\n\n"
            f"## STARTUPS — rondas abiertas en plataformas reguladas (España/UE)\n{j(pool['startups'])}\n\n"
            f"## CLONAR — negocios que funcionan (ideas del radar con encaje por país, ingresos verificados de TrustMRR, últimas tandas de Y Combinator, Product Hunt)\n{j(pool['clonar'])}\n\n"
            f"## ACCIONES — radar de valor + calidad + momento ({j(pool['accion_ctx'])})\n{j(pool['accion'])}\n\n"
            f"## PULSO — lo más fuerte de las últimas 36 h\n{j(pool['extra'])}")


def compact_block(pool: dict, now: datetime) -> str:
    """Candidatos recortados para los modelos gratuitos (Groq corta las peticiones de más de ~8.000 tokens)."""
    pick = lambda r, ks: {k: r.get(k) for k in ks if r.get(k) not in (None, "", [])}  # noqa: E731
    by_src = lambda tag, n: [r for r in pool["clonar"] if tag in (r.get("fuente") or "")][:n]  # noqa: E731
    small = {
        "startups": [pick(r, ("id", "plataforma", "empresa", "titulo", "tipo", "sector", "objetivo_eur", "objetivo_max_eur", "completado_pct",
                              "cierre", "ticket_min_eur")) for r in pool["startups"][:8]],
        "clonar": [pick(r, ("id", "fuente", "nombre", "que_hace", "ingresos_30d_usd", "pais_origen", "encaje"))
                   for r in by_src("Ideas", 8) + by_src("TrustMRR", 6) + by_src("Combinator", 6)],
        "accion": [pick(x, ("id", "nombre", "sector", "precio_usd", "nota_radar", "senal", "cuchillo_cayendo", "valor_razonable_usd"))
                   | {"per": (x.get("metricas") or {}).get("pe"), "stop": (x.get("tecnico") or {}).get("stop")} for x in pool["accion"][:6]],
        "extra": [pick(x, ("id", "titular", "nota")) for x in pool["extra"][:6]],
    }
    local = now.astimezone(MADRID)
    return f"FECHA: {local:%Y-%m-%d %H:%M} (Madrid)\n\nCANDIDATOS (resumidos):\n" + json.dumps(small, ensure_ascii=False, separators=(",", ":"))


_GROQ_LAST = [0.0]


def ask_free(cfg: dict, shared: str, small: str, user: str, transport=None) -> tuple[dict | None, list[str]]:
    """Respaldo gratuito: Gemini (hasta 3 modelos, porque a veces responde 503) con todo; Groq u OpenRouter con lo resumido."""
    router = Router(cfg, transport=transport)
    errs: list[str] = []
    if router.available("gemini"):
        for m in ((cfg.get("models") or {}).get("gemini_preference") or ["gemini-2.5-flash"])[:3]:
            router.chosen["gemini"] = m
            try:
                return router.ask("gemini", RULES + "\n\n" + shared, user), errs
            except Exception as e:  # noqa: BLE001
                errs.append(f"gemini {m}: {str(e)[:90]}")
    for p in ("groq", "openrouter"):
        if router.available(p):
            if p == "groq" and transport is None:  # el plan gratuito de Groq corta a ~8.000 tokens por minuto
                wait = 62 - (time.time() - _GROQ_LAST[0])
                if wait > 0:
                    time.sleep(wait)
                _GROQ_LAST[0] = time.time()
            try:
                return router.ask(p, RULES + "\n\n" + small, user), errs
            except Exception as e:  # noqa: BLE001
                errs.append(f"{p}: {str(e)[:90]}")
    return None, errs or ["sin claves de modelos gratuitos"]


def user_block(profile: dict, grants_list: list[dict]) -> str:
    pub = {k: v for k, v in profile.items() if k not in ("notify",)}
    lang = "español de España" if profile.get("language", "es") == "es" else "English"
    return (f"PERFIL:\n{json.dumps(pub, ensure_ascii=False)}\n\nIdioma de la respuesta: {lang}.\n\n"
            f"## AYUDAS — convocatorias abiertas de la BDNS que podría pedir\n{json.dumps(grants_list, ensure_ascii=False, separators=(',', ':'))}\n\n"
            "Elige lo que de verdad le sirve hoy y responde con el JSON pedido.")


def fingerprint(pool: dict, grants_list: list[dict]) -> str:
    top_clone = [r.get("url") for src in ("Ideas", "TrustMRR", "Combinator", "Product Hunt")
                 for r in [x for x in pool["clonar"] if src in (x.get("fuente") or "")][:10]]
    ids = sorted({str(i) for i in [r.get("url") for r in pool["startups"]] + top_clone +
                  [f"{s['ticker']}:{s.get('tipo_senal')}" for s in pool["accion"][:8]] + [g["id"] for g in grants_list]})
    return hashlib.sha1("|".join(ids).encode()).hexdigest()[:16]


def slots_due(last: datetime | None, now: datetime, times: list[str]) -> bool:
    """¿Ha pasado alguna hora programada (de Madrid) desde el último informe?"""
    if last is None:
        return True
    local = now.astimezone(MADRID)
    marks = []
    for day in (local.date() - timedelta(days=1), local.date()):
        for t in times:
            hh, mm = (int(x) for x in t.split(":"))
            marks.append(datetime(day.year, day.month, day.day, hh, mm, tzinfo=MADRID))
    past = [m for m in marks if m <= local]
    return bool(past) and last < max(past)


def check_due(data_dir: Path, cfg: dict, now: datetime | None = None) -> bool:
    now = now or now_utc()
    bcfg = {**DEFAULTS, **(cfg.get("brief") or {})}
    p = data_dir / "brief.json"
    if not p.exists():
        return True
    try:
        prev = json.loads(p.read_text(encoding="utf-8") or "null")
    except ValueError:
        prev = None
    if not isinstance(prev, dict):
        return False  # no se puede leer: mejor no lanzar nada (queda la hora programada)
    tried = parse_iso(prev.get("attemptedAt"))
    if tried and now - tried < timedelta(minutes=45):
        return False
    return slots_due(parse_iso(prev.get("checkedAt") or prev.get("generatedAt")), now, bcfg["times"])


def run(data_dir: Path, cfg: dict, *, feed_path: Path | None = None, only: str | None = None, force: bool = False,
        now: datetime | None = None, transport=None) -> dict:
    now = now or now_utc()
    bcfg = {**DEFAULTS, **(cfg.get("brief") or {})}
    profiles = cfg.get("profiles") or [{"id": "es", "name": "España", "country": "ES", "language": "es", "currency": "EUR",
                                        "capital": (cfg.get("profile") or {}).get("budget", 2000)}]
    path = data_dir / "brief.json"
    prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    prev.update({"attemptedAt": iso(now)})
    path.write_text(json.dumps(prev, ensure_ascii=False, indent=1), encoding="utf-8")

    today = now.astimezone(MADRID).date().isoformat()
    spend = prev.get("spend") if (prev.get("spend") or {}).get("date") == today else {"date": today, "usd": 0.0}
    pool = gather(data_dir, feed_path, now)
    shared = shared_block(pool, now)
    small = compact_block(pool, now)
    out = {"version": 1, "generatedAt": prev.get("generatedAt"), "checkedAt": iso(now), "attemptedAt": iso(now), "spend": spend,
           "profiles": dict(prev.get("profiles") or {}), "sources": STATUS, "model": bcfg["model"]}
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    changed_any = False
    for prof in profiles:
        pid = prof["id"]
        if only and pid != only:
            continue
        try:
            gl = grants(prof, now)
            _ok(f"ayudas_{pid}", len(gl))
        except Exception as e:  # noqa: BLE001
            gl = []
            _ok(f"ayudas_{pid}", 0, e)
        fp = fingerprint(pool, gl)
        old = (prev.get("profiles") or {}).get(pid) or {}
        fresh = parse_iso(old.get("generatedAt"))
        if not force and old.get("fingerprint") == fp and fresh and now - fresh < timedelta(hours=26) and old.get("ok"):
            continue  # nada nuevo desde el último informe: no se gasta nada
        refs = {"startups": {r["id"] for r in pool["startups"]}, "clonar": {r["id"] for r in pool["clonar"]},
                "accion": {s["id"] for s in pool["accion"] if s.get("tipo_senal") in BREAKOUT and not s.get("cuchillo_cayendo")},
                "ayudas": {g["id"] for g in gl}, "extra": {p["id"] for p in pool["extra"]}}
        cand_urls = {u for sec in ("startups", "clonar", "accion", "extra") for r in pool[sec] for u in (r.get("url"), r.get("web")) if u}
        cand_urls |= {u for g in gl for u in (g.get("url"), g.get("sede"), g.get("bases")) if u}
        user = user_block(prof, gl)
        res, err = None, None
        if has_key and spend["usd"] + 0.6 <= float(bcfg["daily_usd_cap"]):
            try:
                res = ask_claude(shared, user, model=bcfg["model"], effort=bcfg["effort"], max_searches=int(bcfg["max_searches"]),
                                 max_tokens=int(bcfg["max_tokens"]), transport=transport)
                res["cost"] = cost_usd(bcfg["model"], res["usage"], bcfg.get("prices"))
                spend["usd"] = round(spend["usd"] + res["cost"], 4)
            except Exception as e:  # noqa: BLE001
                err = f"Claude: {str(e)[:200]}"
                res = None
        elif has_key:
            err = f"tope diario de {bcfg['daily_usd_cap']} $ alcanzado"
        if res is None:
            r2, ferrs = ask_free(cfg, shared, small, user, transport=transport)
            if r2:
                res = {"data": r2["data"], "usage": {}, "urls": set(), "model": r2.get("model"), "provider": r2.get("provider"), "cost": 0.0}
            else:
                err = (err + " · " if err else "") + "respaldo sin respuesta: " + "; ".join(ferrs[-4:])
        if res is None:
            out["profiles"][pid] = {**old, "ok": bool(old.get("ok")), "error": err, "checkedAt": iso(now)}
            continue
        brief = clean_brief(res["data"], refs=refs, allowed_urls=cand_urls | res["urls"])
        by_ref = {r["id"]: r for sec in ("startups", "clonar", "accion", "extra") for r in pool[sec]} | {g["id"]: g for g in gl}
        es = (prof.get("language") or "es") == "es"
        for sk, sec in brief["secciones"].items():
            for pk in sec["picks"]:
                c = by_ref.get(pk["ref"] or "")
                pk["enlace"] = (c.get("url") if c else None) or (pk["fuentes"][0] if pk["fuentes"] else None)
                if c:
                    ver = verified_facts(sk, c, es)
                    pk["datos"] = dict(list({**ver, **{k: v for k, v in pk["datos"].items() if k not in ver}}.items())[:8])
        if res["provider"] != "anthropic" or brief.get("descartados_por_validacion"):
            brief["resumen"] = plain_summary(brief, es)
        st = res["usage"].get("server_tool_use") or {}
        entry = {"profile": {k: prof.get(k) for k in ("id", "name", "flag", "language", "country")},
                 "generatedAt": iso(now), "checkedAt": iso(now), "ok": True, "error": err, "fingerprint": fp,
                 "provider": res["provider"], "model": res["model"], "cost_usd": res.get("cost", 0.0), "searches": st.get("web_search_requests", 0),
                 "tokens": {k: res["usage"].get(k, 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens")},
                 "candidates": {k: len(v) for k, v in (("startups", pool["startups"]), ("clonar", pool["clonar"]), ("accion", pool["accion"]),
                                                     ("ayudas", gl), ("extra", pool["extra"]))},
                 **brief}
        titles = [p["titulo"] for s in brief["secciones"].values() for p in s["picks"]]
        if titles != [p["titulo"] for s in (old.get("secciones") or {}).values() for p in s.get("picks", [])]:
            changed_any = True
            notify_profile(prof, entry, cfg)
        out["profiles"][pid] = entry
        out["generatedAt"] = iso(now)
    out["spend"] = spend
    out["sources"] = STATUS
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    out["changed"] = changed_any
    return out


def notify_profile(prof: dict, entry: dict, cfg: dict) -> None:
    env = prof.get("notify")
    topic = os.environ.get(env or "", "").strip() if env else ""
    if not topic:
        return
    secs = entry["secciones"]
    es = (prof.get("language") or "es") == "es"
    names = {"startups": ("Startup", "Startup"), "clonar": ("Clonar", "Clone"), "accion": ("Acción", "Stock"), "ayudas": ("Ayuda", "Grant"),
             "extra": ("Además", "Also")}
    lines = [f"{names[k][0 if es else 1]}: {p['titulo']}" for k, s in secs.items() for p in s["picks"]]
    msg = entry.get("resumen") or ""
    if lines:
        msg += "\n\n" + "\n".join("• " + l for l in lines[:8])
    else:
        msg += "\n\n" + ("Hoy no hay nada que merezca la pena." if es else "Nothing worth your time today.")
    app = os.environ.get("APP_URL") or ""
    old = os.environ.get("NTFY_TOPIC")
    try:
        os.environ["NTFY_TOPIC"] = topic
        notify.send(("Para ti" if es else "For you") + f" · {prof.get('name', '')}", msg, priority=3, tags=["dart"],
                    click=(app.rstrip("/") + "/#parati") if app else None)
    finally:
        if old is None:
            os.environ.pop("NTFY_TOPIC", None)
        else:
            os.environ["NTFY_TOPIC"] = old


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--feed", default=None)
    ap.add_argument("--perfil", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check-due", action="store_true")
    a = ap.parse_args(argv)
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8")) if Path(a.config).exists() else {}
    data_dir = Path(a.data)
    data_dir.mkdir(parents=True, exist_ok=True)
    if a.check_due:
        due = check_due(data_dir, cfg)
        print("toca" if due else "no toca")
        sys.exit(0 if due else 1)
    t0 = time.time()
    out = run(data_dir, cfg, feed_path=Path(a.feed) if a.feed else None, only=a.perfil, force=a.force)
    summary = {pid: {"ok": p.get("ok"), "provider": p.get("provider"), "model": p.get("model"), "cost_usd": p.get("cost_usd"),
                     "searches": p.get("searches"), "picks": {k: len(v["picks"]) for k, v in (p.get("secciones") or {}).items()},
                     "error": p.get("error")} for pid, p in out["profiles"].items()}
    print(json.dumps({"segundos": round(time.time() - t0, 1), "gasto_hoy_usd": out["spend"]["usd"], "clave_claude": bool(os.environ.get("ANTHROPIC_API_KEY")),
                      "perfiles": summary, "fuentes": out["sources"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
