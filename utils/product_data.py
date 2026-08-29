"""Estructura de datos que representa un producto ya procesado, lista
para convertirse en un FIND de Telegram.

Los campos de scraping (name, price, images) los rellena el adaptador
de la plataforma correspondiente (ver product_processor/). Los campos
de afiliación/plantilla (spreadsheet_url, sugargoo_url, cupones) se
añaden DESPUÉS, en el handler, a partir de la config del bot — el
scraper nunca debe tocarlos.
"""

from dataclasses import dataclass, field


@dataclass
class ProductData:
    source_url: str  # link original que mandó el usuario (Weidian/Taobao/1688)
    platform: str  # "weidian" | "taobao" | "1688"
    name: str
    price: str  # tal cual se muestra, p.ej. "¥120"
    images: list[str] = field(default_factory=list)

    # Se rellenan en el handler, no en el scraper:
    spreadsheet_url: str = ""
    sugargoo_url: str = ""
    sugargoo_coupon: str = ""
    usfans_coupon: str = ""
