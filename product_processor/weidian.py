"""Adaptador de Weidian.

Descarga nombre, precio e imágenes de un producto de Weidian y, cuando
es posible, detecta la marca automáticamente a partir del nombre o
de las imágenes del producto.
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

# --- Nombre ---
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
    r'https://[a-zA-Z0-9.\-]*geilicdn\.com/[^\s"\'&)]+'
    r'\.(?:jpg|jpeg|png|webp)',
    re.IGNORECASE,
)

_DIMENSION_SUFFIX_RE = re.compile(
    r"_(\d+)_(\d+)\.(?:jpg|jpeg|png|webp)$",
    re.IGNORECASE,
)

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
    """Descarga y procesa la página pública de un producto de Weidian."""

    try:
        async with aiohttp.ClientSession(
            headers=_HEADERS,
            timeout=_TIMEOUT,
        ) as session:
            async with session.get(product_url) as resp:
                if resp.status != 200:
                    raise ProductFetchError(
                        f"Weidian devolvió status {resp.status} para {product_url}"
                    )

                page_html = await resp.text()

    except aiohttp.ClientError as e:
        raise ProductFetchError(
            f"Error de red al pedir {product_url}: {e}"
        ) from e

    # Comprobamos si Weidian ha redirigido a login/registro.
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

    # Extraemos los datos básicos.
    raw_name = _extract_name(page_html)
    price = _extract_price(page_html)
    images = _extract_images(page_html)

    if not raw_name or not price:
        raise ProductFetchError(
            "No se pudo extraer nombre y/o precio del HTML de Weidian "
            "(puede que hayan cambiado la estructura de la página; "
            "usa inspect_weidian.py para revisar el HTML actual)."
        )

    # ---------------------------------------------------------
    # DETECCIÓN DE MARCA
    # ---------------------------------------------------------
    #
    # Primero intentamos obtener la marca directamente del nombre.
    # Esto no consume API y es instantáneo.
    #
    brand = detect_brand_from_name(raw_name)

    # Si el nombre no contiene una marca reconocible, utilizamos
    # la primera imagen real del producto.
    #
    # Esto permite detectar casos como:
    #
    #   "WeightcottonT-shirtbottominglongsleeve..."
    #
    # cuando en la camiseta aparece claramente el logo de
    # Maison Margiela, Nike, Stone Island, etc.
    if not brand and images:
        brand = await detect_brand_from_image(images[0])

    # Construimos el nombre final.
    #
    # El nombre original seguirá estando disponible como descripción.
    # Si encontramos una marca, la colocamos al principio.
    final_name = _build_name_with_brand(raw_name, brand)

    return ProductData(
        source_url=product_url,
        platform="weidian",
        name=final_name,
        price=f"¥{price}",
        images=images,
    )


def _extract_name(page_html: str) -> str:
    """Extrae item_name del JSON embebido."""

    match = (
        _ITEM_NAME_ESCAPED_RE.search(page_html)
        or _ITEM_NAME_NORMAL_RE.search(page_html)
    )

    if not match:
        return ""

    return html_lib.unescape(match.group(1)).strip()


def _format_amount(amount: float) -> str:
    """Formatea un precio en yuanes sin decimales innecesarios."""

    if amount == int(amount):
        return str(int(amount))

    return f"{amount:.2f}"


def _extract_price(page_html: str) -> str:
    """Extrae el precio usando itemLowPrice -> price -> origin_price."""

    # 1. itemLowPrice: céntimos de yuan.
    match = (
        _ITEM_LOW_PRICE_ESCAPED_RE.search(page_html)
        or _ITEM_LOW_PRICE_NORMAL_RE.search(page_html)
    )

    if match:
        cents = int(match.group(1))
        return _format_amount(cents / 100)

    # 2. price: yuanes.
    match = (
        _PRICE_FIELD_ESCAPED_RE.search(page_html)
        or _PRICE_FIELD_NORMAL_RE.search(page_html)
    )

    if match:
        return _format_amount(float(match.group(1)))

    # 3. origin_price: yuanes.
    match = (
        _ORIGIN_PRICE_ESCAPED_RE.search(page_html)
        or _ORIGIN_PRICE_NORMAL_RE.search(page_html)
    )

    if match:
        return _format_amount(float(match.group(1)))

    return ""


def _extract_images(page_html: str) -> list[str]:
    """Extrae únicamente imágenes reales de producto."""

    images: list[str] = []
    seen_keys: set[str] = set()

    for match in _IMG_URL_RE.finditer(page_html):
        url = match.group(0).split("?")[0]
        url_lower = url.lower()

        # Descarta logos, avatares, iconos y banners.
        if any(keyword in url_lower for keyword in _JUNK_KEYWORDS):
            continue

        # Descarta imágenes demasiado pequeñas.
        dim_match = _DIMENSION_SUFFIX_RE.search(url)

        if dim_match:
            width = int(dim_match.group(1))
            height = int(dim_match.group(2))

            if (
                width < _MIN_IMAGE_DIMENSION
                or height < _MIN_IMAGE_DIMENSION
            ):
                continue

        # Evita duplicados.
        dedup_key = (
            url_lower[: -len(".webp")]
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


def _build_name_with_brand(raw_name: str, brand: str) -> str:
    """
    Construye el nombre que recibirá el resto del bot.

    Ejemplos:

        raw_name:
        WeightcottonT-shirtbottominglongsleeve300RR88C

        brand:
        MAISON MARGIELA

        resultado:
        MAISON MARGIELA WeightcottonT-shirtbottominglongsleeve300RR88C

    Si no se detecta ninguna marca, devuelve el nombre original.
    """

    raw_name = html_lib.unescape(raw_name).strip()
    brand = brand.strip()

    if not brand:
        return raw_name

    # Evitamos repetir la marca si ya estaba en el nombre.
    if detect_brand_from_name(raw_name):
        return raw_name

    return f"{brand} {raw_name}"
