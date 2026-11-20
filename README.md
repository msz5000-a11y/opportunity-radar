# Opportunity Radar AI · v2

Radar autónomo de oportunidades (cripto, startups, IA, lanzamientos e ideas de negocio) para un residente en España con un presupuesto máximo de 150 €.

**No compra, no envía dinero, no firma transacciones, no se conecta a wallets y nunca pide frases semilla ni claves.** Solo investiga, analiza y te avisa. Los escenarios 2x-300x son simulaciones matemáticas, no predicciones. Nada de esto es asesoramiento financiero.

## Cómo funciona

```
GitHub Actions (cada 3 h, en la nube, con el móvil apagado)
  ├─ Fuentes directas: DEX Screener, GeckoTerminal, CoinGecko, Hacker News, GitHub, RSS, tipo de cambio del BCE
  ├─ Búsqueda IA: Gemini con Google Search descubre oportunidades nuevas
  ├─ Análisis: modelo A (Groq) construye la ficha y puntúa 12 criterios
  ├─ Verificación: modelo B distinto (Gemini con búsqueda) comprueba dominio, equipo, CNMV/ESMA, España
  ├─ Consenso: si los modelos discrepan ≥3 puntos se toma el valor bajo y se pierde la evidencia
  ├─ Seguridad de tokens: GoPlus + honeypot.is (EVM) y RugCheck (Solana)
  ├─ Puntuación determinista (radar/scoring.py): topes por riesgo crítico, falta de evidencias, España, presupuesto
  ├─ Alertas push con ntfy (no repite avisos) · resumen diario y semanal
  └─ Publica la app (PWA) y los datos en GitHub Pages
```

## Secretos (Settings → Secrets and variables → Actions)

| Secreto | Obligatorio | Para qué |
|---|---|---|
| `GEMINI_API_KEY` | Sí | Búsqueda web y verificación (aistudio.google.com, gratis) |
| `GROQ_API_KEY` | Sí | Análisis (console.groq.com, gratis) |
| `NTFY_TOPIC` | Sí | Canal privado de alertas en la app ntfy |
| `OPENROUTER_API_KEY` | No | Modelo de respaldo gratuito |

## Costes

0 € con los niveles gratuitos de GitHub (repositorio público: minutos de Actions ilimitados), Gemini, Groq y ntfy. Los topes de llamadas por ejecución están en `config.json`. No se activa nada de pago.

## Pruebas

```
pip install -r requirements.txt
python -m pytest -q tests
python -m radar.pipeline --mode check
```
