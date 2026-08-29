"""Excepción común a todos los adaptadores de plataforma.

Contrato que debe cumplir cada adaptador (weidian.py y, en el futuro,
taobao.py / platform_1688.py): exponer una función

    async def fetch(product_url: str) -> ProductData

que lance ProductFetchError si algo falla, en vez de dejar escapar
excepciones de red/parseo sin envolver. Así el handler solo necesita
capturar un tipo de error, sea cual sea la plataforma.
"""


class ProductFetchError(Exception):
    """No se pudo obtener la información del producto."""
