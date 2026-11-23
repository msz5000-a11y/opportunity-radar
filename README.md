# Opportunity Radar AI · v3

Radar autónomo de oportunidades para un residente en España con un presupuesto máximo de 2.000 €. Cubre cripto, bolsa de EE. UU., startups y ayudas, IA, lanzamientos e ideas de negocio. Vigila mercados, noticias y redes sociales casi en tiempo real.

**No compra, no envía dinero, no firma transacciones, no se conecta a wallets y nunca pide frases semilla ni claves.** Solo investiga, analiza y avisa. Nada de esto es asesoramiento financiero.

## Cómo funciona

```
Pulso (pulse.yml, cada 5 min: es el mínimo que permite GitHub)
  ├─ ~60 fuentes gratuitas en paralelo:
  │    · Mercados: CoinGecko, miedo y codicia, altas de Coinbase/Kraken/OKX/Bitget/KuCoin,
  │      anuncios de Binance y OKX, DefiLlama
  │    · Bolsa de EE. UU. (Finnhub, Massive): cotizaciones, noticias, IPO, resultados, compras de directivos
  │    · Redes: StockTwits, Reddit (vía ApeWisdom), Bluesky, Mastodon, Hacker News, GitHub, Hugging Face
  │    · Noticias: ~34 RSS + Google News
  │    · Ayudas públicas: BDNS
  ├─ Deduplica entre fuentes e idiomas, puntúa con reglas y una IA barata (Groq) filtra y resume en español
  ├─ Avisa por ntfy solo de lo muy fuerte (máx. 3/h y 18/día; de noche solo lo excepcional)
  ├─ Guarda el estado en la rama `live` (sin historial)
  └─ Publica la app y los datos en GitHub Pages (único workflow que despliega)

Análisis profundo (radar.yml, cada 3 h)
  ├─ Candidatas: lo más accionable del pulso + descubrimiento con IA
  ├─ Modelo A (Groq) construye la ficha; modelo B distinto (Gemini) la verifica
  ├─ Selección estricta (9 criterios) con manual paso a paso
  └─ Mercados (valor + calidad + momento) e «Ideas para copiar», una vez al día
```

La app (`app/`) tiene una pestaña por categoría: En vivo, Top, Cripto, Bolsa, Startups, IA, Lanzamientos, Ideas, Noticias y Redes. Muestra lo más reciente arriba y comprueba novedades cada minuto.

## Secretos (Settings → Secrets and variables → Actions)

| Secreto | Obligatorio | Para qué |
|---|---|---|
| `GEMINI_API_KEY` | Sí | Verificación y respaldo de la IA (aistudio.google.com, gratis) |
| `GROQ_API_KEY` | Sí | Análisis y filtro del pulso (console.groq.com, gratis) |
| `NTFY_TOPIC` | Sí | Canal privado de alertas en la app ntfy |
| `FINNHUB_API_KEY` | Recomendado | Bolsa: cotizaciones, noticias, calendarios y fundamentales (gratis) |
| `MASSIVE_API_KEY` | Recomendado | Cierres diarios de EE. UU. (gratis) |
| `OPENROUTER_API_KEY` | No | Modelo de respaldo gratuito |

## Costes

0 € con los niveles gratuitos de GitHub (repositorio público), Gemini, Groq, Finnhub, Massive y ntfy. Los límites de uso están en `config.json` (sección `pulse` y `limits`).

## Pruebas

```
pip install -r requirements.txt
python -m pytest -q tests
python -m radar.pulse --live /tmp/live --data data --dry
```
