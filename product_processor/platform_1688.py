"""Adaptador de 1688.

Obtiene nombre, precio e imágenes de un producto de 1688
mediante Playwright.
"""

import re
from urllib.parse import urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from product_processor.base import ProductFetchError
from utils.product_data import ProductData


_MAX_IMAGES = 9
_PAGE_TIMEOUT = 15000

_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)


def _normalise_url(url: str) -> str:
    """Normaliza la URL."""

    if not url:
        return ""

    url = url.strip()

    if not url:
        return ""

    parsed = urlparse(url)

    if not parsed.scheme:
        return "https://" + url

    return url


def _clean_price(value: str) -> str:
    """Extrae un precio numérico."""

    if not value:
        return ""

    value = value.replace(",", ".")

    match = re.search(r"\d+(?:\.\d+)?", value)

    if not match:
        return ""

    return match.group(0)


def _clean_image_url(url: str) -> str:
    """Normaliza una URL de imagen."""

    if not url:
        return ""

    url = url.strip()

    if url.startswith("//"):
        url = "https:" + url

    return url.split("?")[0]


def _is_product_image(url: str) -> bool:
    """Comprueba si una imagen parece ser del producto."""

    if not url:
        return False

    lowered = url.lower()

    if not lowered.startswith(("http://", "https://")):
        return False

    # Elementos habituales de interfaz.
    junk = (
        "logo",
        "avatar",
        "icon",
        "favicon",
        "sprite",
        "loading",
        "qrcode",
        "qr-code",
        "placeholder",
        "default",
        "banner",
        "ad.",
        "ads.",
        "advert",
        "recommend",
        "shop",
        "seller",
        "store",
    )

    if any(word in lowered for word in junk):
        return False

    # No aceptar SVG como foto de producto.
    if lowered.endswith(".svg"):
        return False

    return True


def _image_key(url: str) -> str:
    """Genera una clave para detectar duplicados."""

    cleaned = _clean_image_url(url).lower()

    # 1688 puede servir la misma imagen con diferentes
    # parámetros de tamaño.
    cleaned = re.sub(
        r"[_-]\d+x\d+(?=\.(?:jpg|jpeg|png|webp)$)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned


def _deduplicate_images(images: list[str]) -> list[str]:
    """Elimina imágenes duplicadas y basura evidente."""

    result = []
    seen = set()

    for image in images:

        image = _clean_image_url(image)

        if not _is_product_image(image):
            continue

        key = _image_key(image)

        if key in seen:
            continue

        seen.add(key)
        result.append(image)

    return result


async def _extract_title(page) -> str:
    """Obtiene el nombre del producto."""

    try:
        title = await page.locator(
            'meta[property="og:title"]'
        ).get_attribute("content")

        if title:
            return title.strip()

    except Exception:
        pass

    try:
        title = await page.locator(
            'meta[name="title"]'
        ).get_attribute("content")

        if title:
            return title.strip()

    except Exception:
        pass

    try:
        title = await page.locator("h1").first.inner_text(
            timeout=3000
        )

        title = re.sub(r"\s+", " ", title).strip()

        if title:
            return title

    except Exception:
        pass

    try:
        title = await page.title()

        if title:
            return title.strip()

    except Exception:
        pass

    return ""


async def _extract_price(page) -> str:
    """Obtiene el precio del producto."""

    selectors = [
        'meta[property="product:price:amount"]',
        '[class*="price"]',
        '[class*="Price"]',
    ]

    for selector in selectors:

        try:
            locator = page.locator(selector)
            count = await locator.count()

            for index in range(min(count, 15)):

                element = locator.nth(index)

                value = await element.get_attribute("content")

                if not value:
                    try:
                        value = await element.inner_text(
                            timeout=500
                        )
                    except Exception:
                        value = ""

                price = _clean_price(value or "")

                if price:
                    return price

        except Exception:
            continue

    try:
        html = await page.content()

        patterns = [
            r'"price"\s*:\s*"([\d.]+)"',
            r'"price"\s*:\s*([\d.]+)',
            r'"currentPrice"\s*:\s*"([\d.]+)"',
            r'"currentPrice"\s*:\s*([\d.]+)',
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                html,
                re.IGNORECASE,
            )

            if match:
                price = _clean_price(match.group(1))

                if price:
                    return price

    except Exception:
        pass

    return ""


async def _extract_images(page) -> list[str]:
    """Obtiene imágenes intentando priorizar la galería del producto."""

    images = []

    # ---------------------------------------------------------
    # 1. Open Graph
    # ---------------------------------------------------------

    try:
        elements = await page.locator(
            'meta[property="og:image"]'
        ).all()

        for element in elements:

            url = await element.get_attribute("content")

            if url:
                images.append(url)

    except Exception:
        pass

    # ---------------------------------------------------------
    # 2. Imágenes visibles del DOM
    #
    # Damos prioridad a imágenes realmente visibles.
    # Las recomendaciones/banners suelen estar fuera de la
    # zona visible o tener dimensiones muy pequeñas.
    # ---------------------------------------------------------

    try:
        elements = await page.locator("img").all()

        visible_images = []
        other_images = []

        for element in elements:

            url = await element.get_attribute("src")

            if not url:
                url = await element.get_attribute("data-src")

            if not url:
                url = await element.get_attribute("data-lazy-src")

            if not url:
                url = await element.get_attribute("data-original")

            if not url:
                continue

            try:
                if await element.is_visible():
                    visible_images.append(url)
                else:
                    other_images.append(url)

            except Exception:
                other_images.append(url)

        # Las visibles tienen prioridad.
        images.extend(visible_images)

        # Añadimos las demás solo como respaldo.
        images.extend(other_images)

    except Exception:
        pass

    return _deduplicate_images(images)


async def fetch(product_url: str) -> ProductData:
    """Obtiene los datos de un producto de 1688."""

    product_url = _normalise_url(product_url)

    if not product_url:
        raise ProductFetchError(
            "La URL de 1688 está vacía."
        )

    try:

        async with async_playwright() as p:

            browser = await p.chromium.launch(
                headless=True,
            )

            context = await browser.new_context(
                user_agent=_USER_AGENT,
                locale="zh-CN",
                viewport={
                    "width": 390,
                    "height": 844,
                },
                is_mobile=True,
                device_scale_factor=3,
            )

            page = await context.new_page()

            try:

                await page.goto(
                    product_url,
                    wait_until="domcontentloaded",
                    timeout=_PAGE_TIMEOUT,
                )

                await page.wait_for_timeout(1000)

                # -----------------------------------------
                # EXTRAER DATOS
                # -----------------------------------------

                title = await _extract_title(page)
                price = await _extract_price(page)
                images = await _extract_images(page)

                # -----------------------------------------
                # 1688
                # -----------------------------------------
                #
                # Las primeras 5 imágenes obtenidas son
                # elementos de interfaz de 1688.
                #
                # Se mantiene esta lógica porque en 1688
                # estamos comprobando que esas 5 primeras
                # imágenes son basura.
                # -----------------------------------------

                images = images[5:]

                # Máximo 9 imágenes.
                images = images[:_MAX_IMAGES]

                # -----------------------------------------
                # VALIDACIÓN
                # -----------------------------------------

                if not title:
                    raise ProductFetchError(
                        "No se pudo obtener el nombre "
                        "del producto de 1688."
                    )

                if not price:
                    raise ProductFetchError(
                        "No se pudo obtener el precio "
                        "del producto de 1688."
                    )

                return ProductData(
                    source_url=product_url,
                    platform="1688",
                    name=title,
                    price=f"¥{price}",
                    images=images,
                )

            finally:

                await context.close()
                await browser.close()

    except PlaywrightTimeoutError as e:

        raise ProductFetchError(
            "1688 tardó demasiado en responder."
        ) from e

    except ProductFetchError:
        raise

    except Exception as e:

        raise ProductFetchError(
            f"Error al obtener el producto de 1688: {e}"
        ) from e

