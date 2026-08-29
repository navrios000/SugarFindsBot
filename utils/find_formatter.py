"""Convierte un ProductData ya completo en el texto final del FIND.

Genera un caption en HTML (parse_mode="HTML" de Telegram), pensado
para usarse como caption del primer elemento de un media group de
fotos — así "Spreadsheet" y "SugarGoo" salen como texto clicable en
vez de URLs largas visibles.
"""

import html as html_lib

from utils.product_data import ProductData


def build_find_caption(product: ProductData) -> str:
    """Texto del FIND (sin las fotos, que se envían aparte como media
    group). Orden pedido: Spreadsheet -> nombre -> precio -> SugarGoo
    -> cupones."""

    name = html_lib.escape(product.name)

    lines = [
        f'📊 <a href="{product.spreadsheet_url}">Spreadsheet</a>',
        "",
        f"🏷️ {name}",
        "",
        f"💰 {product.price}",
        "",
        f'🔗 <a href="{product.sugargoo_url}">SugarGoo</a>',
        "",
        f"🎟️ SugarGoo Coupon: {product.sugargoo_coupon}",
        f"🎟️ USFans Coupon: {product.usfans_coupon}",
    ]
    return "\n".join(lines)
