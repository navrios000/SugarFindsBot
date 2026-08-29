"""Punto único de entrada: dado un enlace ya identificado por
utils.link_parser, delega en el adaptador correcto.

Añadir una plataforma nueva = escribir product_processor/<nombre>.py
con un `async def fetch(product_url) -> ProductData` y registrarlo en
_ADAPTERS. No hay que tocar el handler ni el resto de adaptadores.
"""

from product_processor import weidian
from utils.link_parser import Platform
from utils.product_data import ProductData

_ADAPTERS = {
    Platform.WEIDIAN: weidian.fetch,
    # Platform.TAOBAO y Platform.ALIBABA_1688 todavía no tienen
    # adaptador automático (decisión actual: manual por ahora, ver
    # handlers/message_handler.py).
}


class UnsupportedPlatformError(Exception):
    """La plataforma se reconoce, pero todavía no está automatizada."""


async def process(platform: Platform, product_url: str) -> ProductData:
    adapter = _ADAPTERS.get(platform)
    if adapter is None:
        raise UnsupportedPlatformError(
            f"La plataforma '{platform.value}' todavía no tiene scraping automático."
        )
    return await adapter(product_url)
