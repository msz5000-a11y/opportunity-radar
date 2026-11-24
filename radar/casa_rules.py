"""Reglas compartidas de «Desde casa» (el pulso y el informe): intereses en inglés, idiomas y qué titular es un caso real."""
from __future__ import annotations

import re
import unicodedata

INTEREST_EN = {"inmobiliaria": "real estate", "arte": "art", "diseno": "design", "ninos": "kids", "cocina": "cooking", "reposteria": "baking",
               "fotografia": "photography", "moda": "fashion", "educacion": "education", "musica": "music", "jardineria": "gardening",
               "manualidades": "crafts", "belleza": "beauty", "salud": "wellness", "mascotas": "pets", "viajes": "travel", "idiomas": "languages",
               "costura": "sewing", "ilustracion": "illustration", "decoracion": "home decor", "bienestar": "wellness", "yoga": "yoga"}
HL = {"en": ("en-US", "US", "US:en"), "es": ("es", "ES", "ES:es"), "fr": ("fr", "FR", "FR:fr"), "it": ("it", "IT", "IT:it"),
      "pt": ("pt-BR", "BR", "BR:pt-419")}

CASE_SIGNAL = re.compile(r"[$€£₹]\s?\d|\d+\s?(k|mil|million|millones|figures|cifras)\b|a month|per month|al mes|par mois|al mese|por mês|six[- ]figure|"
                         r"from home|desde casa|depuis chez|da casa|de casa|home[- ]based|kitchen table|side hustle|etsy|sold out|turned .{3,40} into|"
                         r"convirti[oó]|empez[oó]|lanz[oó]|fund[oó]|launched|started|founded|quit (her|his) job|dej[oó] su trabajo", re.I)
CASE_BIZ = re.compile(r"business|negocio|shop|tienda|brand|marca|company|empresa|startup|hustle|emprend|entrepreneur|etsy|store|sells|vende|selling|"
                      r"entreprise|attivit|negócio|boutique|bakery|panader|studio|estudio|course|curso|clases|classes", re.I)
LISTICLE = re.compile(r"^\s*(the\s+)?\d+\s+\w+|\bideas\b|\bways to\b|\bformas de\b|\btips\b|\bconsejos\b|\bguía\b|\bguide\b|\bbest\b|\bmejores\b", re.I)


def fold(s: str) -> str:
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


def en(word: str) -> str:
    return INTEREST_EN.get(fold(word).strip(), word)


def looks_like_case(title: str) -> bool:
    """Titular de una historia concreta (alguien que montó algo y le funciona), no una lista de ideas ni una entrevista corporativa."""
    return bool(CASE_SIGNAL.search(title or "") and CASE_BIZ.search(title or "")) and not LISTICLE.search(title or "")


def story_queries(prof: dict) -> list[tuple[str, str]]:
    """Búsquedas de historias reales de negocios desde casa según los intereses del perfil (varios idiomas)."""
    qs: list[tuple[str, str]] = []
    for i in [x for x in (prof.get("interests") or []) if x][:6]:
        qs += [("en", f'"from home" {en(i)} business (earns OR revenue OR "a month" OR success)'), ("es", f'"desde casa" {i} negocio (éxito OR factura OR clientes)'),
               ("en", f'{en(i)} "side hustle" (earns OR "a month")')]
    qs += [("en", '"home-based business" success story "a month"'), ("en", 'started a business from home "now earns"'),
           ("en", 'mom quit her job business from home'), ("es", 'emprendedora "desde casa" factura'), ("es", 'negocio online desde casa éxito clientas'),
           ("fr", '"depuis chez elle" entreprise succès'), ("it", '"da casa" attività guadagna'), ("pt", '"de casa" negócio fatura')]
    return qs


def local_queries(prof: dict) -> list[tuple[str, str]]:
    """Búsquedas de oportunidades en su zona: programas, ayudas, formación, mercados y ferias."""
    muni, prov, reg = prof.get("municipality"), prof.get("province"), prof.get("region_name")
    qs: list[tuple[str, str]] = []
    if muni:
        qs += [("es", f'"{muni}" (emprendimiento OR emprendedoras OR autónomos OR comercio)'), ("es", f'"{muni}" (ayudas OR subvenciones OR curso OR taller)')]
    if prov:
        qs += [("es", f'"{prov}" emprendedoras (programa OR ayudas OR formación)'), ("es", f'mercado artesanal OR feria artesanos "{prov}"')]
    if reg:
        qs += [("es", f'"{reg}" (autónomos OR emprendimiento) ayudas convocatoria')]
    return qs
