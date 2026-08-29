"""Detecta la plataforma de un enlace (Weidian/Taobao/1688) y extrae la
URL del producto de un mensaje de texto.

Este módulo SOLO identifica y extrae. No hace scraping ni llamadas de
red: esa lógica vive en product_processor/. Así se puede añadir una
plataforma nueva sin tocar el scraping existente, y viceversa.
"""

import re
from enum import Enum
from typing import Optional


class Platform(str, Enum):
    WEIDIAN = "weidian"
    TAOBAO = "taobao"
    ALIBABA_1688 = "1688"
    UNKNOWN = "unknown"


_URL_RE = re.compile(r"https?://[^\s]+")

# Nota: si en el futuro quieres tratar tmall.com como parte de la
# familia "taobao" (comparten protecciones anti-bot), añádelo aquí.
_DOMAIN_MAP = {
    "weidian.com": Platform.WEIDIAN,
    "taobao.com": Platform.TAOBAO,
    "1688.com": Platform.ALIBABA_1688,
}


def _match_platform(url: str) -> Platform:
    for domain, platform in _DOMAIN_MAP.items():
        if domain in url:
            return platform
    return Platform.UNKNOWN


def find_product_link(text: str) -> Optional[tuple[Platform, str]]:
    """Busca el primer enlace reconocible en `text`.

    Devuelve (Platform, url) o None si no hay ningún enlace de
    Weidian/Taobao/1688 en el mensaje.
    """
    if not text:
        return None

    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(").,;\u3002")  # limpia puntuación pegada al link
        platform = _match_platform(url)
        if platform is not Platform.UNKNOWN:
            return platform, url

    return None
