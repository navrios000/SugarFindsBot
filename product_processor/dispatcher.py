"""Punto único de entrada para procesar productos.

Recibe una plataforma ya identificada por utils.link_parser
y delega el scraping en el adaptador correspondiente.
"""

from product_processor import platform_1688
from product_processor import taobao
from product_processor import weidian

from utils.link_parser import Platform
from utils.product_data import ProductData


_ADAPTERS = {
    Platform.WEIDIAN: weidian.fetch,
    Platform.TAOBAO: taobao.fetch,
    Platform.ALIBABA_1688: platform_1688.fetch,
}


class UnsupportedPlatformError(Exception):
    """La plataforma no tiene adaptador automático."""


async def process(
    platform: Platform,
    product_url: str,
) -> ProductData:

    adapter = _ADAPTERS.get(platform)

    if adapter is None:
        raise UnsupportedPlatformError(
            f"La plataforma '{platform.value}' "
            "todavía no tiene scraping automático."
        )

    return await adapter(product_url)
