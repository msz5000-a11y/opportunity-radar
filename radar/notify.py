"""Notificaciones push con ntfy (app gratuita para Android e iOS; funciona con el móvil bloqueado).

Variables: NTFY_TOPIC (obligatoria, nombre largo y aleatorio = tu canal privado),
NTFY_SERVER (opcional, por defecto https://ntfy.sh), NTFY_TOKEN (opcional, si usas un servidor con acceso).
"""
from __future__ import annotations

import os

from . import net

SENT: list[dict] = []  # registro en memoria (útil en pruebas)
LAST: dict = {}  # diagnóstico del último intento (sin datos secretos)


def send(title: str, message: str, *, priority: int = 3, tags: list[str] | None = None, click: str | None = None) -> bool:
    raw = os.environ.get("NTFY_TOPIC") or ""
    topic = raw.strip()
    LAST.clear()
    LAST.update({"topicSet": bool(topic), "topicLength": len(raw), "topicHadSpaces": raw != topic,
                 "topicLooksRight": topic.startswith("radar-") and len(topic) == 28, "ok": False})
    if not topic:
        LAST["error"] = "falta el secreto NTFY_TOPIC"
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    body = {"topic": topic, "title": title[:250], "message": message[:3900], "priority": max(1, min(5, priority)),
            "tags": tags or [], "markdown": False}
    if click:
        body["click"] = click
        body["actions"] = [{"action": "view", "label": "Abrir en la app", "url": click}]
    headers = {"Content-Type": "application/json"}
    if os.environ.get("NTFY_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['NTFY_TOKEN']}"
    try:
        r = net.request("POST", server, json=body, headers=headers, retries=3, timeout=20)
        SENT.append(body)
        LAST.update({"ok": True, "status": getattr(r, "status_code", None)})
        return True
    except Exception as e:
        LAST["error"] = str(e)[:200]
        print(f"[ntfy] no se pudo enviar: {e}")
        return False
