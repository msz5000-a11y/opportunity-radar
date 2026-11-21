"""Cliente multi-modelo: Gemini (con búsqueda de Google), Groq, OpenRouter y, opcionalmente, Anthropic.

Cada proveedor se activa solo si su clave existe en el entorno. Hay un tope de llamadas por ejecución
para no salirse de los niveles gratuitos, reintentos con espera ante 429/5xx y elección automática del
modelo disponible a partir de una lista de preferencias (los catálogos cambian a menudo).
"""
from __future__ import annotations

import json
import os
import re
import time

from . import net

KEYS = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


class LLMError(Exception):
    pass


class BudgetExceeded(LLMError):
    pass


def extract_json(text: str):
    """Saca el primer objeto/array JSON de una respuesta, tolerando ```json y texto alrededor."""
    if text is None:
        raise LLMError("respuesta vacía")
    t = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = t.find(open_c)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(t)):
                ch = t[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                elif ch == '"':
                    in_str = True
                elif ch == open_c:
                    depth += 1
                elif ch == close_c:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(t[start:i + 1])
                        except json.JSONDecodeError:
                            break
            start = t.find(open_c, start + 1)
    raise LLMError("no se encontró JSON válido en la respuesta")


class Router:
    def __init__(self, config: dict, transport=None):
        self.cfg = config
        self.limits = config.get("limits", {}).get("max_llm_calls", {})
        self.models_cfg = config.get("models", {})
        self.calls = {p: 0 for p in KEYS}
        self.errors: list[str] = []
        self.chosen: dict[str, str] = {}
        self.search_blocked = False  # la búsqueda de Google de Gemini sin cupo: se sigue sin ella
        self.transport = transport or net.request  # inyectable en pruebas

    # ---------------------------------------------------------- disponibilidad
    def available(self, provider: str) -> bool:
        return bool(os.environ.get(KEYS[provider])) and self.limits.get(provider, 0) > self.calls[provider]

    def first_available(self, role: str, exclude: set[str] | None = None) -> str | None:
        for p in self.models_cfg.get(role, []):
            if p in KEYS and self.available(p) and p not in (exclude or set()):
                return p
        return None

    def _count(self, provider: str):
        if self.calls[provider] >= self.limits.get(provider, 0):
            raise BudgetExceeded(f"tope de llamadas alcanzado para {provider}")
        self.calls[provider] += 1

    def _post(self, url, *, headers, body, timeout=90):
        r = self.transport("POST", url, headers=headers, json=body, timeout=timeout, retries=3)
        return r.json()

    def _get(self, url, *, headers):
        return self.transport("GET", url, headers=headers, timeout=30, retries=2).json()

    # ---------------------------------------------------------- elección de modelo
    def _pick(self, provider: str, listed: list[str]) -> str:
        if provider in self.chosen:
            return self.chosen[provider]
        prefs = self.models_cfg.get(f"{provider}_preference", [])
        model = next((m for m in prefs if m in listed), None)
        if not model and listed:
            if provider == "gemini":
                model = next((m for m in listed if "flash" in m and "image" not in m and "tts" not in m and "live" not in m), listed[0])
            else:
                model = listed[0]
        if not model:
            model = prefs[0] if prefs else ""
        self.chosen[provider] = model
        return model

    def _gemini_model(self) -> str:
        if "gemini" in self.chosen:
            return self.chosen["gemini"]
        try:
            data = self._get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                             headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
            listed = [m["name"].split("/", 1)[1] for m in data.get("models", [])
                      if "generateContent" in (m.get("supportedGenerationMethods") or [])]
        except Exception as e:
            self.errors.append(f"gemini listado: {e}")
            listed = []
        return self._pick("gemini", listed)

    def _openai_model(self, provider: str, base: str, key: str) -> str:
        if provider in self.chosen:
            return self.chosen[provider]
        try:
            data = self._get(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
            listed = [m["id"] for m in data.get("data", [])]
            if provider == "openrouter":
                listed = [m for m in listed if m.endswith(":free") or m == "openrouter/free"] or listed
        except Exception as e:
            self.errors.append(f"{provider} listado: {e}")
            listed = []
        return self._pick(provider, listed)

    # ---------------------------------------------------------- llamadas
    def ask(self, provider: str, system: str, prompt: str, *, search: bool = False, temperature: float = 0.2,
            require_search: bool = False) -> dict:
        """Devuelve {"data": <json>, "model": str, "provider": str, "grounding": [{"title","url"}]}.

        Si la búsqueda de Google de Gemini responde 429 (sin cupo), se repite la petición sin búsqueda, salvo que
        el rol la necesite (descubrir oportunidades nuevas sin buscar llevaría a inventarlas)."""
        if provider == "gemini" and search and self.search_blocked:
            if require_search:
                raise LLMError("búsqueda de Google sin cupo en Gemini")
            search = False
        try:
            return self._ask(provider, system, prompt, search=search, temperature=temperature)
        except Exception as e:  # noqa: BLE001
            if provider == "gemini" and search and "429" in str(e):
                self.search_blocked = True
                self.errors.append("gemini: búsqueda de Google sin cupo (429); se continúa sin búsqueda")
                if require_search:
                    raise
                return self._ask(provider, system, prompt, search=False, temperature=temperature)
            raise

    def _ask(self, provider: str, system: str, prompt: str, *, search: bool = False, temperature: float = 0.2) -> dict:
        self._count(provider)
        key = os.environ.get(KEYS[provider], "")
        grounding = []
        if provider == "gemini":
            model = self._gemini_model()
            body = {"systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature}}
            if search:
                body["tools"] = [{"google_search": {}}]
            else:
                body["generationConfig"]["responseMimeType"] = "application/json"
            data = self._post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                              headers={"x-goog-api-key": key, "Content-Type": "application/json"}, body=body)
            cand = (data.get("candidates") or [{}])[0]
            text = "".join(p.get("text", "") for p in ((cand.get("content") or {}).get("parts") or []))
            for ch in ((cand.get("groundingMetadata") or {}).get("groundingChunks") or []):
                web = ch.get("web") or {}
                if web.get("uri"):
                    grounding.append({"title": web.get("title") or "", "url": web["uri"]})
        elif provider in ("groq", "openrouter"):
            base = "https://api.groq.com/openai/v1" if provider == "groq" else "https://openrouter.ai/api/v1"
            model = self._openai_model(provider, base, key)
            body = {"model": model, "temperature": temperature,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}}
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            if provider == "openrouter":
                headers.update({"HTTP-Referer": "https://github.com", "X-Title": "Opportunity Radar AI"})
            data = self._post(f"{base}/chat/completions", headers=headers, body=body)
            text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        elif provider == "anthropic":
            model = self.models_cfg.get("anthropic_model", "claude-haiku-5-5")
            self.chosen["anthropic"] = model
            data = self._post("https://api.anthropic.com/v1/messages",
                              headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                              body={"model": model, "max_tokens": 4000, "system": system,
                                    "messages": [{"role": "user", "content": prompt + "\n\nResponde solo con JSON."}]})
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        else:
            raise LLMError(f"proveedor desconocido: {provider}")
        return {"data": extract_json(text), "model": self.chosen.get(provider, ""), "provider": provider, "grounding": grounding}

    def ask_role(self, role: str, system: str, prompt: str, *, search: bool = False, exclude: set[str] | None = None,
                 require_search: bool = False) -> dict | None:
        """Prueba los proveedores del rol en orden; si uno falla, pasa al siguiente."""
        tried = set(exclude or set())
        while True:
            p = self.first_available(role, tried)
            if not p:
                return None
            tried.add(p)
            try:
                if require_search and p != "gemini":
                    continue
                return self.ask(p, system, prompt, search=search and p == "gemini", require_search=require_search)
            except BudgetExceeded:
                continue
            except Exception as e:
                self.errors.append(f"{role}/{p}: {str(e)[:160]}")
                time.sleep(1)
                continue

    def resolve_redirect(self, url: str) -> str:
        """Las fuentes de Gemini llegan como enlaces de redirección: obtener la URL final."""
        if "vertexaisearch.cloud.google.com" not in url:
            return url
        try:
            r = net._session.head(url, allow_redirects=True, timeout=10)
            return r.url or url
        except Exception:
            return url

    def usage(self) -> dict:
        return {"calls": {k: v for k, v in self.calls.items() if v}, "models": self.chosen, "errors": self.errors[-10:],
                "googleSearch": not self.search_blocked}
