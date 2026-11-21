"""HTTP con reintentos, límites de ritmo, respeto de robots.txt para páginas HTML y registro por fuente."""
from __future__ import annotations

import re
import time
import urllib.robotparser
from html import unescape
from urllib.parse import urlparse

import requests

UA = "OpportunityRadarAI/2.0 (+uso personal; investigación de oportunidades; contacto vía GitHub)"
_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"})
_last_call: dict[str, float] = {}
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
MIN_INTERVAL = 1.2  # segundos entre llamadas al mismo host


class FetchError(Exception):
    pass


def _throttle(host: str):
    wait = MIN_INTERVAL - (time.time() - _last_call.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.time()


def request(method: str, url: str, *, retries: int = 3, timeout: int = 25, **kw) -> requests.Response:
    host = urlparse(url).netloc
    last = None
    for attempt in range(retries):
        _throttle(host)
        try:
            r = _session.request(method, url, timeout=timeout, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                retry_after = r.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** (attempt + 1)
                last = FetchError(f"HTTP {r.status_code}")
                time.sleep(min(delay, 30))
                continue
            if r.status_code >= 400:
                raise FetchError(f"HTTP {r.status_code}")
            return r
        except requests.RequestException as e:
            last = FetchError(str(e)[:200])
            time.sleep(2 ** attempt)
    raise last or FetchError("sin respuesta")


def get_json(url: str, **kw):
    kw["headers"] = {"Accept": "application/json", **(kw.get("headers") or {})}
    return request("GET", url, **kw).json()


def allowed_by_robots(url: str) -> bool:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = _session.get(base + "/robots.txt", timeout=10)
            if r.status_code >= 400:
                _robots[base] = None  # sin robots.txt: permitido
            else:
                rp.parse(r.text.splitlines())
                _robots[base] = rp
        except requests.RequestException:
            _robots[base] = None
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(UA, url)


def page_text(url: str, max_chars: int = 6000) -> str:
    """Texto legible de una página HTML, solo si robots.txt lo permite."""
    if not url or not url.startswith(("http://", "https://")):
        return ""
    if not allowed_by_robots(url):
        return "[robots.txt no permite leer esta página automáticamente]"
    try:
        r = request("GET", url, retries=2, timeout=20)
    except FetchError as e:
        return f"[no se pudo leer: {e}]"
    ctype = r.headers.get("Content-Type", "")
    if "html" not in ctype and "text" not in ctype:
        return f"[contenido no textual: {ctype}]"
    html = r.text
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    title = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = unescape(re.sub(r"\s+", " ", text)).strip()
    head = f"TÍTULO: {unescape(title.group(1).strip())}\n" if title else ""
    return (head + text)[:max_chars]
