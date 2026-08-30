"""Formato final de los FINDs de SugarFindsBot."""

import html

from utils.product_data import ProductData


SPREADSHEET_LABEL = "SPREADSHEET +3000 LINKS"
SUGARGOO_LABEL = "SUGARGOO"
USFANS_LABEL = "USFANS"
SUGARGOO_COUPON_LABEL = "SUGARGOO COUPON"
USFANS_COUPON_LABEL = "USFANS COUPON"


def build_find_caption(product: ProductData) -> str:
    """Construye el texto final del FIND."""

    name = html.escape(product.name)

    lines = [
        f'📊 <a href="{product.spreadsheet_url}">{SPREADSHEET_LABEL}</a>',
        "",
        f"🏷️ {name}",
        "",
        f"💰 {product.price}",
        "",
        f'🔗 <a href="{product.sugargoo_url}">{SUGARGOO_LABEL}</a>',
    ]

    if product.usfans_url:
        lines.append(
            f'🔗 <a href="{product.usfans_url}">{USFANS_LABEL}</a>'
        )

    lines.extend(
        [
            "",
            f'🎟️ <a href="{product.sugargoo_coupon}">'
            f'{SUGARGOO_COUPON_LABEL}</a>',
            f'🎟️ <a href="{product.usfans_coupon}">'
            f'{USFANS_COUPON_LABEL}</a>',
        ]
    )

    return "\n".join(lines)
