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
_PAGE_TIMEOUT = 30000


_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)


def _clean_price(value: str) -> str:
    """Extrae un precio numérico."""

    if not value:
        return ""

    value = value.replace(",", ".")

    match = re.search(
        r"\d+(?:\.\d+)?",
        value,
    )

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
    """Comprueba si una imagen parece ser realmente del producto."""

    if not url:
        return False

    lowered = url.lower()

    if not lowered.startswith(
        ("http://", "https://")
    ):
        return False

    # Imágenes que normalmente NO son productos.
    junk = (
        "logo",
        "avatar",
        "icon",
        "favicon",
        "sprite",
        "loading",
        "qrcode",
        "qr-code",
        "seller",
        "shop",
        "default",
        "placeholder",
        "blank",
        "empty",
        "loading",
        "head",
        "nav",
        "banner",
        "flag",
    )

    if any(word in lowered for word in junk):
        return False

    # 1688 / Alibaba utiliza principalmente estos dominios.
    valid_domains = (
        "alicdn.com",
        "taobao.com",
        "tbcdn.cn",
        "cbu01.alicdn.com",
        "gw.alicdn.com",
        "img.alicdn.com",
    )

    if not any(
        domain in lowered
        for domain in valid_domains
    ):
        return False

    return True


def _deduplicate_images(
    images: list[str],
) -> list[str]:
    """Elimina imágenes basura y duplicadas."""

    result: list[str] = []
    seen: set[str] = set()

    for image in images:

        image = _clean_image_url(image)

        if not _is_product_image(image):
            continue

        key = image.lower()

        if key in seen:
            continue

        seen.add(key)

        result.append(image)

        if len(result) >= _MAX_IMAGES:
            break

    return result


def _normalise_url(url: str) -> str:
    """Normaliza la URL."""

    url = url.strip()

    parsed = urlparse(url)

    if not parsed.scheme:
        return "https://" + url

    return url


async def _extract_title(page) -> str:
    """Obtiene el nombre del producto."""

    # Open Graph
    try:

        value = await page.locator(
            'meta[property="og:title"]'
        ).first.get_attribute("content")

        if value:
            value = value.strip()

            if value:
                return value

    except Exception:
        pass

    # Meta title
    try:

        value = await page.locator(
            'meta[name="title"]'
        ).first.get_attribute("content")

        if value:
            value = value.strip()

            if value:
                return value

    except Exception:
        pass

    # H1
    try:

        value = await page.locator(
            "h1"
        ).first.inner_text(
            timeout=5000
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

        if value:
            return value

    except Exception:
        pass

    # Título HTML
    try:

        value = await page.title()

        value = re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

        if value:
            return value

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

            for index in range(
                min(count, 30)
            ):

                element = locator.nth(index)

                value = await element.get_attribute(
                    "content"
                )

                if not value:

                    try:

                        value = await element.inner_text(
                            timeout=1000
                        )

                    except Exception:

                        value = ""

                cleaned = _clean_price(value)

                if cleaned:
                    return cleaned

        except Exception:
            continue

    # Buscar directamente en HTML.
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

                cleaned = _clean_price(
                    match.group(1)
                )

                if cleaned:
                    return cleaned

    except Exception:
        pass

    return ""


async def _extract_images(page) -> list[str]:
    """Obtiene únicamente imágenes reales del producto."""

    images: list[str] = []

    # -------------------------------------------------
    # OPEN GRAPH
    # -------------------------------------------------

    try:

        meta_images = page.locator(
            'meta[property="og:image"]'
        )

        count = await meta_images.count()

        for index in range(count):

            element = meta_images.nth(index)

            url = await element.get_attribute(
                "content"
            )

            if url:
                images.append(url)

    except Exception:
        pass

    # -------------------------------------------------
    # IMÁGENES DEL DOM
    # -------------------------------------------------

    try:

        image_elements = page.locator("img")

        count = await image_elements.count()

        for index in range(
            min(count, 150)
        ):

            element = image_elements.nth(index)

            for attribute in (
                "src",
                "data-src",
                "data-lazy-src",
                "data-original",
            ):

                url = await element.get_attribute(
                    attribute
                )

                if url:
                    images.append(url)
                    break

    except Exception:
        pass

    # -------------------------------------------------
    # FILTRADO
    # -------------------------------------------------

    return _deduplicate_images(images)


async def fetch(product_url: str) -> ProductData:
    """Obtiene los datos de un producto de 1688."""

    product_url = _normalise_url(
        product_url
    )

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

                await page.wait_for_timeout(
                    4000
                )

                # -------------------------------------------------
                # EXTRAER
                # -------------------------------------------------

                title = await _extract_title(
                    page
                )

                price = await _extract_price(
                    page
                )

                images = await _extract_images(
                    page
                )

                # -------------------------------------------------
                # VALIDACIÓN
                # -------------------------------------------------

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
