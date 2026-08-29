"""Adaptador de Weidian.

Comprobado manualmente: una petición HTTP normal (sin sesión, sin
navegador) a la URL de un item de Weidian devuelve el HTML con los
datos del producto embebidos en JSON — probablemente el estado inicial
de la SPA, servido para SEO / vistas compartidas. Por eso este
adaptador usa aiohttp (ya es dependencia del proyecto) en vez de
Playwright: para Weidian no hace falta navegador.

ESTRUCTURA REAL CONFIRMADA (inspect_weidian.py contra un producto real,
itemID=7805672623) — el HTML trae el JSON con las comillas escapadas
como entidades HTML (&#34; en vez de "), así que todos los patrones se
buscan primero en su forma escapada y, si no aparece, en forma de JSON
normal (por si Weidian sirve el HTML sin escapar en otro caso):

    item_name&#34;:&#34;【DX39】WeightcottonT-shirtbottominglongsleeve300RR88C&#34;
    itemLowPrice&#34;:14900,&#34;itemSellable&#34;:true
    origin_price&#34;:&#34;149&#34;
    price&#34;:&#34;149.00&#34;                      (aparece varias veces)
    https://si.geilicdn.com/.....-999_999.jpg        (fotos reales)
    https://si.geilicdn.com/.....-unadjust_74_74.png (icono/logo, se descarta)

`itemLowPrice` está en céntimos de yuan (14900 = ¥149.00) y es la
fuente más fiable cuando existe. Si no aparece, se cae a `price` y
luego a `origin_price`, que ya vienen en yuanes.

Ya no se usa <meta property="og:title"> / "og:image": en el HTML real
no hace falta y añadía una dependencia que no se ha podido confirmar.
"""

import html as html_lib
import re

import aiohttp

from product_processor.base import ProductFetchError
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

# --- Nombre: item_name en el JSON embebido (escapado o normal) ---
_ITEM_NAME_ESCAPED_RE = re.compile(r"item_name&#34;\s*:\s*&#34;(.*?)&#34;")
_ITEM_NAME_NORMAL_RE = re.compile(r'"item_name"\s*:\s*"(.*?)"')

# --- Precio: itemLowPrice (céntimos) -> price (yuanes) -> origin_price (yuanes) ---
_ITEM_LOW_PRICE_ESCAPED_RE = re.compile(r"itemLowPrice&#34;\s*:\s*(\d+)")
_ITEM_LOW_PRICE_NORMAL_RE = re.compile(r'"itemLowPrice"\s*:\s*(\d+)')

_PRICE_FIELD_ESCAPED_RE = re.compile(r"(?<!Low)price&#34;\s*:\s*&#34;([\d.]+)&#34;", re.IGNORECASE)
_PRICE_FIELD_NORMAL_RE = re.compile(r'(?<!Low)"price"\s*:\s*"([\d.]+)"', re.IGNORECASE)

_ORIGIN_PRICE_ESCAPED_RE = re.compile(r"origin_price&#34;\s*:\s*&#34;([\d.]+)&#34;")
_ORIGIN_PRICE_NORMAL_RE = re.compile(r'"origin_price"\s*:\s*"([\d.]+)"')

# --- Imágenes: geilicdn.com, descartando iconos/banners/avatares/logos ---
#
# BUG encontrado con el HTML real: la clase de caracteres anterior no
# excluía "&", así que cuando dos URLs venían separadas por &#34;,&#34;
# (comillas escapadas, no comillas normales) la regex se tragaba todo
# seguido como si fuera una sola URL gigante con varias fotos
# concatenadas. Al excluir "&" del charset, la coincidencia se corta
# justo antes de cada &#34;, y cada foto sale como una URL individual.
_IMG_URL_RE = re.compile(
    r'https://[a-zA-Z0-9.\-]*geilicdn\.com/[^\s"\'&)]+\.(?:jpg|jpeg|png|webp)', re.IGNORECASE
)
_DIMENSION_SUFFIX_RE = re.compile(r"_(\d+)_(\d+)\.(?:jpg|jpeg|png|webp)$", re.IGNORECASE)

# Palabras que SOLO aparecen en assets que no son fotos de producto,
# confirmadas en el HTML real (iconos "hz_img_..._unadjust", el propio
# "unadjust" del banner 550x200, el avatar por defecto "wx_default_headimg"
# y el logo por defecto "vshop-shop-logo-default"). Se comprueban en
# minúsculas para que dé igual la capitalización.
_JUNK_KEYWORDS = ("unadjust", "hz_img", "default", "headimg", "logo")

# Los iconos/logos observados son 74x74/96x52/42x42; las fotos reales
# de producto observadas son >=999x999. 200px es un margen amplio y
# seguro entre ambos casos (solo aplica cuando SÍ hay sufijo de
# dimensiones pegado a la extensión; la lista negra de arriba cubre
# los casos, como el banner 550x200, donde el sufijo no está pegado).
# amplio y seguro entre ambos casos.
_MIN_IMAGE_DIMENSION = 200

_MAX_IMAGES = 9  # Telegram permite hasta 10 fotos por media group


async def fetch(product_url: str) -> ProductData:
    """Descarga y parsea la página pública de un producto de Weidian."""
    try:
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT) as session:
            async with session.get(product_url) as resp:
                if resp.status != 200:
                    raise ProductFetchError(
                        f"Weidian devolvió status {resp.status} para {product_url}"
                    )
                page_html = await resp.text()
    except aiohttp.ClientError as e:
        raise ProductFetchError(f"Error de red al pedir {product_url}: {e}") from e

    # Si redirige a login/registro, esta URL en concreto sí necesita
    # sesión (no debería ser lo normal, pero mejor fallar con un
    # mensaje claro que devolver datos vacíos).
    head = page_html[:3000].lower()
    if "login.taobao" in head or "/register" in head or "<title>register</title>" in head:
        raise ProductFetchError(
            "Weidian redirigió a login/register para este producto: "
            "la vista pública no está disponible."
        )

    name = _extract_name(page_html)
    price = _extract_price(page_html)
    images = _extract_images(page_html)

    if not name or not price:
        raise ProductFetchError(
            "No se pudo extraer nombre y/o precio del HTML de Weidian "
            "(puede que hayan cambiado la estructura de la página; "
            "usa inspect_weidian.py para revisar el HTML actual)."
        )

    return ProductData(
        source_url=product_url,
        platform="weidian",
        name=name,
        price=f"¥{price}",
        images=images,
    )


def _extract_name(page_html: str) -> str:
    match = _ITEM_NAME_ESCAPED_RE.search(page_html) or _ITEM_NAME_NORMAL_RE.search(page_html)
    if not match:
        return ""
    # el valor puede traer sus propias entidades HTML dentro (&amp;, etc.)
    return html_lib.unescape(match.group(1)).strip()


def _format_amount(amount: float) -> str:
    """149.0 -> '149'; 149.5 -> '149.50'. Evita ceros decimales de sobra
    cuando el precio es un número entero de yuanes."""
    if amount == int(amount):
        return str(int(amount))
    return f"{amount:.2f}"


def _extract_price(page_html: str) -> str:
    # 1) itemLowPrice: viene en céntimos de yuan (14900 -> ¥149.00)
    match = _ITEM_LOW_PRICE_ESCAPED_RE.search(page_html) or _ITEM_LOW_PRICE_NORMAL_RE.search(
        page_html
    )
    if match:
        cents = int(match.group(1))
        return _format_amount(cents / 100)

    # 2) price: ya viene en yuanes como string, p.ej. "149.00"
    match = _PRICE_FIELD_ESCAPED_RE.search(page_html) or _PRICE_FIELD_NORMAL_RE.search(page_html)
    if match:
        return _format_amount(float(match.group(1)))

    # 3) origin_price: también en yuanes, p.ej. "149"
    match = _ORIGIN_PRICE_ESCAPED_RE.search(page_html) or _ORIGIN_PRICE_NORMAL_RE.search(page_html)
    if match:
        return _format_amount(float(match.group(1)))

    return ""


def _extract_images(page_html: str) -> list[str]:
    images: list[str] = []
    seen_keys: set[str] = set()

    for match in _IMG_URL_RE.finditer(page_html):
        url = match.group(0).split("?")[0]  # quita parámetros de tamaño si los hubiera
        url_lower = url.lower()

        if any(keyword in url_lower for keyword in _JUNK_KEYWORDS):
            continue  # icono / avatar / logo / banner, no es foto de producto

        dim_match = _DIMENSION_SUFFIX_RE.search(url)
        if dim_match:
            width, height = int(dim_match.group(1)), int(dim_match.group(2))
            if width < _MIN_IMAGE_DIMENSION or height < _MIN_IMAGE_DIMENSION:
                continue  # icono/decorativo pequeño (p.ej. 74x74)

        # La misma foto puede aparecer dos veces con distinta extensión
        # (".../999_999.jpg" y ".../999_999.jpg.webp"); se deduplica
        # quitando un ".webp" final antes de comparar, para no contar
        # la misma foto dos veces.
        dedup_key = url_lower[: -len(".webp")] if url_lower.endswith(".webp") else url_lower
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        images.append(url)

        if len(images) >= _MAX_IMAGES:
            break

    return images
