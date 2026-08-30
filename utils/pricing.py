"""Conversión de precio de yuanes (¥) a euros (€)."""

import re

_NUMBER_RE = re.compile(r"[\d]+(?:\.[\d]+)?")


def cny_to_eur(cny_price: str, rate: float) -> str:
    """Convierte un precio en yuanes a euros."""

    match = _NUMBER_RE.search(cny_price)

    if not match:
        return cny_price

    amount_cny = float(match.group(0))
    amount_eur = amount_cny * rate

    return f"{amount_eur:.2f}".replace(".", ",") + " €"
