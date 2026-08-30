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


MAX_IMAGES = 9
PAGE_TIMEOUT = 15000

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)


def _normalise_url(url: str) -> str:
    """Normaliza la URL."""

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

    match = re.search(
        r"\d+(?:\.\d+)?",
        value,
    )

    return match.group(0) if match else ""


def _clean_image_url(url: str) -> str:
    """Limpia una URL de imagen."""

    if not url:
        return ""

    url = url.strip()

    if url.startswith("//"):
        url = "https:" + url

    return url.split("?")[0]


def _is_product_image(url: str) -> bool:
    """Comprueba si parece una imagen del producto."""

    if not url:
        return False

    url = url.lower()

    if not url.startswith(("http://", "https://")):
        return False

    unwanted = (
        "logo",
        "avatar",
        "icon",
        "favicon",
        "sprite",
        "loading",
        "qrcode",
    )

    return not any(
        word in url
        for word in unwanted
    )


def _unique_images(images: list[str]) -> list[str]:
    """Elimina duplicados y limita las imágenes."""

    result = []
    seen = set()

    for image in images:

        image = _clean_image_url(image)

        if not _is_product_image(image):
            continue

        key = image.lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(image)

        if len(result) >= MAX_IMAGES:
            break

    return result


async def _extract_title(page) -> str:
    """Obtiene el nombre del producto."""

    # Open Graph
    try:

        title = await page.locator(
            'meta[property="og:title"]'
        ).get_attribute("content")

        if title:
            return title.strip()

    except Exception:
        pass

    # H1
    try:

        title = await page.locator(
            "h1"
        ).first.inner_text(
            timeout=2000
        )

        title = re.sub(
            r"\s+",
            " ",
            title,
        ).strip()

        if title:
            return title

    except Exception:
        pass

    # Título HTML
    try:

        title = await page.title()

        if title:
            return title.strip()

    except Exception:
        pass

    return ""


async def _extract_price(page) -> str:
    """Obtiene el precio del producto."""

    selectors = (
        'meta[property="product:price:amount"]',
        'meta[itemprop="price"]',
        '[itemprop="price"]',
        '[class*="price"]',
        '[class*="Price"]',
    )

    for selector in selectors:

        try:

            elements = page.locator(selector)

            count = await elements.count()

            for index in range(
                min(count, 20)
            ):

                element = elements.nth(index)

                value = await element.get_attribute(
                    "content"
                )

                if not value:

                    try:
                        value = await element.inner_text(
                            timeout=500
                        )
                    except Exception:
                        value = ""

                price = _clean_price(
                    value or ""
                )

                if price:
                    return price

        except Exception:
            continue

    # Buscar precio dentro del HTML.
    try:

        html = await page.content()

        patterns = (
            r'"price"\s*:\s*"([\d.]+)"',
            r'"price"\s*:\s*([\d.]+)',
            r'"currentPrice"\s*:\s*"([\d.]+)"',
            r'"currentPrice"\s*:\s*([\d.]+)',
        )

        for pattern in patterns:

            match = re.search(
                pattern,
                html,
                re.IGNORECASE,
            )

            if match:
                return _clean_price(
                    match.group(1)
                )

    except Exception:
        pass

    return ""


async def _extract_images(page) -> list[str]:
    """Obtiene imágenes del producto."""

    images = []

    # Open Graph
    try:

        elements = page.locator(
            'meta[property="og:image"]'
        )

        count = await elements.count()

        for index in range(count):

            url = await elements.nth(index).get_attribute(
                "content"
            )

            if url:
                images.append(url)

    except Exception:
        pass

    # Imágenes de la página
    try:

        elements = page.locator("img")

        count = await elements.count()

        for index in range(
            min(count, 80)
        ):

            element = elements.nth(index)

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

    return _unique_images(images)


async def fetch(product_url: str) -> ProductData:
    """Obtiene un producto de 1688."""

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
                user_agent=USER_AGENT,
                locale="zh-CN",
                viewport={
                    "width": 390,
                    "height": 844,
                },
                is_mobile=True,
                device_scale_factor=2,
            )

            page = await context.new_page()

            try:

                await page.goto(
                    product_url,
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT,
                )

                # Solo una pequeña espera para contenido dinámico.
                await page.wait_for_timeout(500)

                title = await _extract_title(page)
                price = await _extract_price(page)
                images = await _extract_images(page)

                if not title:
                    raise ProductFetchError(
                        "1688 no permitió obtener "
                        "el nombre del producto."
                    )

                if not price:
                    raise ProductFetchError(
                        "1688 no permitió obtener "
                        "el precio del producto."
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
