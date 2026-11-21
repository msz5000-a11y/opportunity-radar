"""Búsqueda web con Tavily (plan gratuito: 1.000 créditos/mes; una búsqueda básica = 1 crédito).

Sustituye a la búsqueda de Google de Gemini, que en el plan gratuito responde 429.
Variable: TAVILY_API_KEY. Sin clave, devuelve una lista vacía y el radar sigue con sus otras fuentes.
"""
from __future__ import annotations

import os

from . import net

USED = {"calls": 0}
MAX_CALLS_PER_RUN = 12  # tope por ejecución para no agotar el cupo mensual


def available() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY"))


def tavily(query: str, *, max_results: int = 6, time_range: str | None = "month", topic: str = "general") -> list[dict]:
    """Devuelve [{"title", "url", "content", "date"}]. Nunca lanza excepciones."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key or USED["calls"] >= MAX_CALLS_PER_RUN:
        return []
    body = {"query": query[:380], "max_results": max(1, min(10, max_results)), "search_depth": "basic", "topic": topic}
    if time_range:
        body["time_range"] = time_range
    USED["calls"] += 1
    try:
        r = net.request("POST", "https://api.tavily.com/search", json=body, retries=2, timeout=30,
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        out = []
        for x in (r.json() or {}).get("results", []) or []:
            url = str(x.get("url") or "")
            if url.startswith("http"):
                out.append({"title": str(x.get("title") or url)[:200], "url": url,
                            "content": str(x.get("content") or "")[:600], "date": x.get("published_date")})
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[tavily] {str(e)[:150]}")
        return []
