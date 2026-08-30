"""Adaptador de Taobao.

Obtiene nombre, precio e imágenes de un producto de Taobao
mediante Playwright.
"""

import re
from urllib.parse import urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from product_processor.base import ProductFetchError
from utils.product_data import ProductData


_MAX_IMAGES = 9

_HEADERS = {
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _clean_price(value: str) -> str:
    """Extrae un precio numérico del texto."""

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

    if url.startswith("//"):
        url = "https:" + url

    return url.split("?")[0]


def _is_product_image(url: str) -> bool:
    """Filtra imágenes que probablemente no sean del producto."""

    if not url:
        return False

    lowered = url.lower()

    if not lowered.startswith(("http://", "https://")):
        return False

    junk = (
        "logo",
        "avatar",
        "icon",
        "favicon",
        "sprite",
        "loading",
        "qrcode",
    )

    return not any(word in lowered for word in junk)


def _deduplicate_images(images: list[str]) -> list[str]:
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

        if len(result) >= _MAX_IMAGES:
            break

    return result


def _normalise_url(url: str) -> str:
    """Convierte enlaces de Taobao móviles en URLs utilizables."""

    parsed = urlparse(url)

    if not parsed.scheme:
        return "https://" + url

    return url


async def fetch(product_url: str) -> ProductData:
    """Obtiene los datos de un producto de Taobao."""

    product_url = _normalise_url(product_url)

    try:
        async with async_playwright() as p:

            browser = await p.chromium.launch(
                headless=True,
            )

            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 "
                    "(KHTML, like Gecko) Version/17.0 "
                    "Mobile/15E148 Safari/604.1"
                ),
                locale="zh-CN",
                extra_http_headers=_HEADERS,
            )

            page = await context.new_page()

            try:
                await page.goto(
                    product_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                await page.wait_for_timeout(3000)

                title = ""

                # Open Graph.
                title = await page.locator(
                    'meta[property="og:title"]'
                ).get_attribute("content") or ""

                # Título HTML.
                if not title:
                    title = await page.title()

                # H1.
                if not title:
                    try:
                        title = await page.locator(
                            "h1"
                        ).first.inner_text(
                            timeout=5000
                        )
                    except Exception:
                        pass

                title = title.strip()

                # Precio.
                price = ""

                price_selectors = [
                    'meta[property="product:price:amount"]',
                    '[class*="price"]',
                    '[class*="Price"]',
                ]

                for selector in price_selectors:
                    try:

                        locator = page.locator(selector)

                        count = await locator.count()

                        for i in range(min(count, 10)):

                            element = locator.nth(i)

                            value = (
                                await element.get_attribute(
                                    "content"
                                )
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
                                price = cleaned
                                break

                        if price:
                            break

                    except Exception:
                        continue

                # Imágenes.
                images = []

                meta_images = await page.locator(
                    'meta[property="og:image"]'
                ).all()

                for element in meta_images:
                    url = await element.get_attribute("content")

                    if url:
                        images.append(url)

                image_elements = await page.locator(
                    "img"
                ).all()

                for element in image_elements:

                    url = await element.get_attribute("src")

                    if not url:
                        url = await element.get_attribute(
                            "data-src"
                        )

                    if url:
                        images.append(url)

                images = _deduplicate_images(images)

                if not title:
                    raise ProductFetchError(
                        "No se pudo obtener el nombre del producto "
                        "de Taobao."
                    )

                if not price:
                    raise ProductFetchError(
                        "No se pudo obtener el precio del producto "
                        "de Taobao."
                    )

                return ProductData(
                    source_url=product_url,
                    platform="taobao",
                    name=title,
                    price=f"¥{price}",
                    images=images,
                )

            finally:
                await context.close()
                await browser.close()

    except PlaywrightTimeoutError as e:

        raise ProductFetchError(
            "Taobao tardó demasiado en responder."
        ) from e

    except ProductFetchError:
        raise

    except Exception as e:

        raise ProductFetchError(
            f"Error al obtener el producto de Taobao: {e}"
        ) from e
