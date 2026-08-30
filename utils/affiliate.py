"""Generación de enlaces de afiliado."""

from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


# Categorías de productos de USFans
USFANS_1688_CATEGORY = "1"
USFANS_TAOBAO_CATEGORY = "2"
USFANS_WEIDIAN_CATEGORY = "3"


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
            keep_blank_values=True,
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


def _build_usfans_product_url(
    item_id: str,
    category: str,
    ref: str,
) -> str:
    """Construye un enlace de producto de USFans."""

    if not item_id:
        return ""

    base_url = (
        f"https://www.usfans.com/product/"
        f"{category}/{item_id}"
    )

    return build_usfans_url(base_url, ref)


def extract_weidian_item_id(weidian_url: str) -> str:
    """Extrae el itemID de una URL de Weidian."""

    parsed = urlsplit(weidian_url)

    params = dict(parse_qsl(parsed.query))

    return params.get("itemID", "")


def extract_1688_item_id(url: str) -> str:
    """Extrae el ID de producto de 1688."""

    parsed = urlsplit(url)

    # Ejemplo:
    # https://detail.1688.com/offer/795915272823.html

    parts = parsed.path.rstrip("/").split("/")

    if "offer" not in parts:
        return ""

    try:
        index = parts.index("offer")

        if index + 1 >= len(parts):
            return ""

        item_id = parts[index + 1]

        # Quitamos .html
        item_id = item_id.split(".")[0]

        return item_id

    except (ValueError, IndexError):
        return ""


def extract_taobao_item_id(url: str) -> str:
    """Extrae el ID de producto de Taobao."""

    parsed = urlsplit(url)

    params = dict(parse_qsl(parsed.query))

    return params.get("id", "")


def build_usfans_product_url(
    product_url: str,
    ref: str,
) -> str:
    """
    Genera el enlace de producto de USFans
    dependiendo de la plataforma de origen.
    """

    parsed = urlsplit(product_url)

    hostname = parsed.netloc.lower()

    # -------------------------------------------------
    # WEIDIAN
    # -------------------------------------------------

    if "weidian.com" in hostname:

        item_id = extract_weidian_item_id(
            product_url
        )

        return _build_usfans_product_url(
            item_id=item_id,
            category=USFANS_WEIDIAN_CATEGORY,
            ref=ref,
        )

    # -------------------------------------------------
    # 1688
    # -------------------------------------------------

    if "1688.com" in hostname:

        item_id = extract_1688_item_id(
            product_url
        )

        return _build_usfans_product_url(
            item_id=item_id,
            category=USFANS_1688_CATEGORY,
            ref=ref,
        )

    # -------------------------------------------------
    # TAOBAO / TMALL
    # -------------------------------------------------

    if (
        "taobao.com" in hostname
        or "tmall.com" in hostname
    ):

        item_id = extract_taobao_item_id(
            product_url
        )

        return _build_usfans_product_url(
            item_id=item_id,
            category=USFANS_TAOBAO_CATEGORY,
            ref=ref,
        )

    # Plataforma desconocida
    return ""
