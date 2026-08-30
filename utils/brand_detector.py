
"""Adaptador de Weidian.

Extrae nombre, precio e imágenes directamente del HTML público de Weidian.
Además intenta detectar la marca:
1. Por el nombre del producto.
2. Si no aparece, mediante la primera imagen usando OpenAI Vision.
"""

import html as html_lib
import re

import aiohttp

from product_processor.base import ProductFetchError
from utils.brand_detector import detect_brand_from_image, detect_brand_from_name
from utils.product_data import ProductData

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_TIMEOUT = aiohttp.ClientTimeout(total=15)

# --- Nombre: item_name en el JSON embebido ---

_ITEM_NAME_ESCAPED_RE = re.compile(
    r"item_name&#34;\s*:\s*&#34;(.*?)&#34;"
)

_ITEM_NAME_NORMAL_RE = re.compile(
    r'"item_name"\s*:\s*"(.*?)"'
)

# --- Precio ---

_ITEM_LOW_PRICE_ESCAPED_RE = re.compile(
    r"itemLowPrice&#34;\s*:\s*(\d+)"
)

_ITEM_LOW_PRICE_NORMAL_RE = re.compile(
    r'"itemLowPrice"\s*:\s*(\d+)'
)

_PRICE_FIELD_ESCAPED_RE = re.compile(
    r"(?<!Low)price&#34;\s*:\s*&#34;([\d.]+)&#34;",
    re.IGNORECASE,
)

_PRICE_FIELD_NORMAL_RE = re.compile(
    r'(?<!Low)"price"\s*:\s*"([\d.]+)"',
    re.IGNORECASE,
)

_ORIGIN_PRICE_ESCAPED_RE = re.compile(
    r"origin_price&#34;\s*:\s*&#34;([\d.]+)&#34;"
)

_ORIGIN_PRICE_NORMAL_RE = re.compile(
    r'"origin_price"\s*:\s*"([\d.]+)"'
)

# --- Imágenes ---

_IMG_URL_RE = re.compile(
    r'https://[a-zA-Z0-9.\-]*geilicdn\.com/[^\s"\'&)]+\.(?:jpg|jpeg|png|webp)',
    re.IGNORECASE,
)

_DIMENSION_SUFFIX_RE = re.compile(
    r"_(\d+)_(\d+)\.(?:jpg|jpeg|png|webp)$",
    re.IGNORECASE,
)

# Assets que NO son fotos del producto.
_JUNK_KEYWORDS = (
    "unadjust",
    "hz_img",
    "default",
    "headimg",
    "logo",
)

_MIN_IMAGE_DIMENSION = 200

_MAX_IMAGES = 9


async def fetch(product_url: str) -> ProductData:
    """Descarga y parsea la página pública de un producto de Weidian."""

    try:
        async with aiohttp.ClientSession(
            headers=_HEADERS,
            timeout=_TIMEOUT,
        ) as session:

            async with session.get(product_url) as resp:

                if resp.status != 200:
                    raise ProductFetchError(
                        f"Weidian devolvió status {resp.status} "
                        f"para {product_url}"
                    )

                page_html = await resp.text()

    except aiohttp.ClientError as e:
        raise ProductFetchError(
            f"Error de red al pedir {product_url}: {e}"
        ) from e

    # Comprobar si Weidian redirigió a login/register.
    head = page_html[:3000].lower()

    if (
        "login.taobao" in head
        or "/register" in head
        or "<title>register</title>" in head
    ):
        raise ProductFetchError(
            "Weidian redirigió a login/register para este producto: "
            "la vista pública no está disponible."
        )

    # Extraer datos.
    name = _extract_name(page_html)
    price = _extract_price(page_html)
    images = _extract_images(page_html)

    if not name or not price:
        raise ProductFetchError(
            "No se pudo extraer nombre y/o precio del HTML de Weidian "
            "(puede que haya cambiado la estructura de la página; "
            "usa inspect_weidian.py para revisar el HTML actual)."
        )

    # ---------------------------------------------------------
    # DETECCIÓN DE MARCA
    # ---------------------------------------------------------

    # Primero intentamos detectar la marca directamente en el nombre.
    brand = detect_brand_from_name(name)

    # Si el nombre no contiene una marca reconocible,
    # analizamos la primera imagen del producto.
    if not brand and images:
        brand = await detect_brand_from_image(images[0])

    # Si hemos encontrado una marca, la colocamos delante.
    if brand:
        if brand.upper() not in name.upper():
            name = f"{brand} {name}"

    # ---------------------------------------------------------

    return ProductData(
        source_url=product_url,
        platform="weidian",
        name=name,
        price=f"¥{price}",
        images=images,
    )


def _extract_name(page_html: str) -> str:
    """Extrae el nombre original del producto."""

    match = (
        _ITEM_NAME_ESCAPED_RE.search(page_html)
        or _ITEM_NAME_NORMAL_RE.search(page_html)
    )

    if not match:
        return ""

    return html_lib.unescape(match.group(1)).strip()


def _format_amount(amount: float) -> str:
    """Formatea un precio en yuanes."""

    if amount == int(amount):
        return str(int(amount))

    return f"{amount:.2f}"


def _extract_price(page_html: str) -> str:
    """Extrae el precio usando varias fuentes de respaldo."""

    # 1. itemLowPrice.
    # Viene en céntimos de yuan.
    match = (
        _ITEM_LOW_PRICE_ESCAPED_RE.search(page_html)
        or _ITEM_LOW_PRICE_NORMAL_RE.search(page_html)
    )

    if match:
        cents = int(match.group(1))
        return _format_amount(cents / 100)

    # 2. price.
    match = (
        _PRICE_FIELD_ESCAPED_RE.search(page_html)
        or _PRICE_FIELD_NORMAL_RE.search(page_html)
    )

    if match:
        return _format_amount(float(match.group(1)))

    # 3. origin_price.
    match = (
        _ORIGIN_PRICE_ESCAPED_RE.search(page_html)
        or _ORIGIN_PRICE_NORMAL_RE.search(page_html)
    )

    if match:
        return _format_amount(float(match.group(1)))

    return ""


def _extract_images(page_html: str) -> list[str]:
    """Extrae las fotos reales del producto."""

    images: list[str] = []
    seen_keys: set[str] = set()

    for match in _IMG_URL_RE.finditer(page_html):

        url = match.group(0).split("?")[0]
        url_lower = url.lower()

        # Eliminar iconos, logos, avatares y banners.
        if any(
            keyword in url_lower
            for keyword in _JUNK_KEYWORDS
        ):
            continue

        # Comprobar dimensiones cuando existen.
        dim_match = _DIMENSION_SUFFIX_RE.search(url)

        if dim_match:

            width = int(dim_match.group(1))
            height = int(dim_match.group(2))

            if (
                width < _MIN_IMAGE_DIMENSION
                or height < _MIN_IMAGE_DIMENSION
            ):
                continue

        # Evitar imágenes duplicadas.
        dedup_key = (
            url_lower[:-len(".webp")]
            if url_lower.endswith(".webp")
            else url_lower
        )

        if dedup_key in seen_keys:
            continue

        seen_keys.add(dedup_key)
        images.append(url)

        if len(images) >= _MAX_IMAGES:
            break

    return images
