# Opportunity Radar AI · v3

Radar autónomo de oportunidades para un residente en España con un presupuesto máximo de 2.000 €. Cubre cripto, bolsa de EE. UU., startups y ayudas, IA, lanzamientos e ideas de negocio. Vigila mercados, noticias y redes sociales casi en tiempo real.

**No compra, no envía dinero, no firma transacciones, no se conecta a wallets y nunca pide frases semilla ni claves.** Solo investiga, analiza y avisa. Nada de esto es asesoramiento financiero.

## Cómo funciona

```
Para ti (brief.yml, cada mañana a las 07:30 de Madrid; el pulso lo lanza si GitHub no lo hace)
  ├─ Candidatos: rondas abiertas (Startupxplore, Capital Cell, Dozen), negocios para clonar (ideas del radar,
  │  TrustMRR con ingresos verificados, últimas tandas de Y Combinator, Product Hunt), acciones del radar de
  │  mercados (con la señal de ruptura), ayudas BDNS abiertas para personas o pymes y lo mejor del pulso
  ├─ Claude (Opus 5.5, con 3 búsquedas web como mucho) elige para cada perfil lo poco que sirve:
  │  startups 2 · clonar 2 · acción 1 · ayudas 3 · además 2 (o nada, con una nota)
  ├─ Solo puede citar enlaces de los candidatos o de sus búsquedas; tope de gasto diario en config.json
  ├─ Sin clave de Claude, decide un modelo gratuito (Gemini, Groq u OpenRouter) sin búsqueda
  └─ data/brief.json → pestaña «Para ti» y un aviso por ntfy si cambia

Desde casa (dentro de brief.yml, cada 3 días por perfil, o al pedir «más ideas» o cambiar el perfil)
  ├─ Historias reales de negocios desde casa (Google News en 5 idiomas, según los intereses; solo titulares
  │  que son un caso concreto) y pequeños negocios con ingresos verificados (TrustMRR)
  ├─ Claude busca más casos en la web y desarrolla 1-3 ideas nuevas: casos enlazados, por qué encaja, cómo
  │  empezar semana a semana, coste, precio, primeras clientas, ingresos posibles, horas, trámites, ayudas y riesgos
  ├─ Una idea sin caso comprobado no se publica; el texto de cada caso sale de la fuente
  └─ Ayudas para emprender de su ayuntamiento, diputación, comunidad autónoma y del Estado (BDNS)

Pulso (pulse.yml, cada 5 min: es el mínimo que permite GitHub)
  ├─ ~60 fuentes gratuitas en paralelo:
  │    · Mercados: CoinGecko, miedo y codicia, altas de Coinbase/Kraken/OKX/Bitget/KuCoin,
  │      anuncios de Binance y OKX, DefiLlama
  │    · Bolsa de EE. UU. (Finnhub, Massive): cotizaciones, noticias, IPO, resultados, compras de directivos
  │    · Hacker News (StockTwits, Reddit, Bluesky, Mastodon, GitHub y Hugging Face, apagados por ruido)
  │    · Noticias: ~34 RSS + Google News
  │    · Ayudas públicas: BDNS
  ├─ Deduplica entre fuentes e idiomas, puntúa con reglas y una IA barata (Groq) filtra y resume en español
  ├─ Avisa por ntfy solo de lo muy fuerte (máx. 2/h y 8/día; de noche solo lo excepcional)
  ├─ Guarda el estado en la rama `live` (sin historial)
  └─ Publica la app y los datos en GitHub Pages (único workflow que despliega)

Análisis profundo (radar.yml, cada 3 h)
  ├─ Candidatas: lo más accionable del pulso + descubrimiento con IA
  ├─ Modelo A (Groq) construye la ficha; modelo B distinto (Gemini) la verifica
  ├─ Selección estricta (9 criterios) con manual paso a paso
  └─ Mercados (valor + calidad + momento) e «Ideas para copiar», una vez al día
```

La app (`app/`) abre en la pestaña que prefiera cada perfil: «Para ti» o «Desde casa». Tiene además En vivo, Cripto, Bolsa, Startups e Ideas. Muestra lo más reciente arriba y comprueba novedades cada minuto.

Los perfiles de cada persona están en `data/profiles.json` (ahora Él, Ella y Egipto). Recogen dónde vive, a qué se dedica, intereses, capital, horas, qué secciones quiere y la pestaña de inicio. Se editan desde la app con «Personalizar»: con el token guardado en Ajustes se suben al repositorio y Claude rehace lo de ese perfil. El repositorio es público, así que los perfiles se pueden ver.

## Secretos (Settings → Secrets and variables → Actions)

| Secreto | Obligatorio | Para qué |
|---|---|---|
| `GEMINI_API_KEY` | Sí | Verificación y respaldo de la IA (aistudio.google.com, gratis) |
| `GROQ_API_KEY` | Sí | Análisis y filtro del pulso (console.groq.com, gratis) |
| `NTFY_TOPIC` | Sí | Canal privado de alertas en la app ntfy |
| `FINNHUB_API_KEY` | Recomendado | Bolsa: cotizaciones, noticias, calendarios y fundamentales (gratis) |
| `MASSIVE_API_KEY` | Recomendado | Cierres diarios de EE. UU. (gratis) |
| `OPENROUTER_API_KEY` | No | Modelo de respaldo gratuito |
| `ANTHROPIC_API_KEY` | Para «Para ti» con Claude | Que decida Claude (platform.claude.com, de pago por uso; sin ella decide un modelo gratuito) |
| `NTFY_TOPIC_EG` | No | Canal ntfy del perfil de Egipto |

## Costes

0 € con los niveles gratuitos de GitHub (repositorio público), Gemini, Groq, Finnhub, Massive y ntfy. Los límites de uso están en `config.json` (sección `pulse` y `limits`).

«Para ti» con Claude es de pago por uso: con Opus 5.5 (4 $ por millón de tokens de entrada y 20 $ de salida; 10 $ por cada 1.000 búsquedas) cada informe cuesta unos 0,25-0,40 $ por perfil y cada tanda de ideas «Desde casa» unos 0,35 $; con los tres perfiles, unos 0,8 $ al día (≈ 25 $ al mes). Si los candidatos no han cambiado, no se llama a Claude. Hay un tope diario (`brief.daily_usd_cap`, 1,5 $) y se puede bajar el gasto a la mitad con `brief.model: claude-sonnet-5-5`.

## Pruebas

```
pip install -r requirements.txt
python -m pytest -q tests
python -m radar.pulse --live /tmp/live --data data --dry
```
