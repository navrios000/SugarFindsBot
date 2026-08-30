"""Generación de enlaces de afiliado."""

from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


def build_sugargoo_url(product_url: str, member_id: str) -> str:
    """Construye el enlace de producto de SugarGoo."""

    # Evita memberId=memberId=...
    if member_id.lower().startswith("memberid="):
        member_id = member_id.split("=", 1)[1]

    # SugarGoo necesita doble URL-encoding
    encoded_once = quote(product_url, safe="")
    encoded_twice = quote(encoded_once, safe="")

    return (
        "https://www.sugargoo.com/products?"
        f"productLink={encoded_twice}"
        f"&memberId={member_id}"
    )


def build_usfans_url(product_url: str, ref: str) -> str:
    """Añade la referencia de afiliado a un enlace de USFans."""

    parsed = urlsplit(product_url)

    query_params = [
        (key, value)
        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True
        )
        if key != "ref"
    ]

    query_params.append(("ref", ref))

    new_query = urlencode(query_params)

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            new_query,
            parsed.fragment,
        )
    )


# Categoría usada actualmente para productos procedentes de Weidian.
USFANS_PRODUCT_CATEGORY = "3"


def extract_weidian_item_id(weidian_url: str) -> str:
    """Extrae el itemID de una URL de Weidian."""

    parsed = urlsplit(weidian_url)

    params = dict(parse_qsl(parsed.query))

    return params.get("itemID", "")


def build_usfans_product_url(
    weidian_url: str,
    ref: str,
) -> str:
    """Genera el enlace de producto de USFans desde Weidian."""

    item_id = extract_weidian_item_id(weidian_url)

    if not item_id:
        return ""

    base_url = (
        f"https://www.usfans.com/product/"
        f"{USFANS_PRODUCT_CATEGORY}/{item_id}"
    )

    return build_usfans_url(base_url, ref)
