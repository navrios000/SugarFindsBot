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


def _clean_price(value: str) -> str:
    if not value:
        return ""

    value = value.replace(",", ".")

    match = re.search(r"\d+(?:\.\d+)?", value)

    if not match:
        return ""

    return match.group(0)


def _clean_image_url(url: str) -> str:
    if not url:
        return ""

    if url.startswith("//"):
        url = "https:" + url

    return url.split("?")[0]


def _is_product_image(url: str) -> bool:
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
    parsed = urlparse(url)

    if not parsed.scheme:
        return "https://" + url

    return url


async def fetch(product_url: str) -> ProductData:
    """Obtiene los datos de un producto de 1688."""

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
            )

            page = await context.new_page()

            try:

                await page.goto(
                    product_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                await page.wait_for_timeout(3000)

                # -------------------------------------------------
                # NOMBRE
                # -------------------------------------------------

                title = ""

                try:
                    title = await page.locator(
                        'meta[property="og:title"]'
                    ).get_attribute("content") or ""
                except Exception:
                    pass

                if not title:
                    try:
                        title = await page.locator(
                            'meta[name="title"]'
                        ).get_attribute("content") or ""
                    except Exception:
                        pass

                if not title:
                    title = await page.title()

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

                # -------------------------------------------------
                # PRECIO
                # -------------------------------------------------

                price = ""

                selectors = [
                    'meta[property="product:price:amount"]',
                    '[class*="price"]',
                    '[class*="Price"]',
                ]

                for selector in selectors:

                    try:

                        locator = page.locator(selector)

                        count = await locator.count()

                        for i in range(min(count, 15)):

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

                # -------------------------------------------------
                # IMÁGENES
                # -------------------------------------------------

                images = []

                try:

                    meta_images = await page.locator(
                        'meta[property="og:image"]'
                    ).all()

                    for element in meta_images:

                        url = await element.get_attribute(
                            "content"
                        )

                        if url:
                            images.append(url)

                except Exception:
                    pass

                try:

                    image_elements = await page.locator(
                        "img"
                    ).all()

                    for element in image_elements:

                        url = await element.get_attribute(
                            "src"
                        )

                        if not url:
                            url = await element.get_attribute(
                                "data-src"
                            )

                        if not url:
                            url = await element.get_attribute(
                                "data-lazy-src"
                            )

                        if url:
                            images.append(url)

                except Exception:
                    pass

                images = _deduplicate_images(images)

                # -------------------------------------------------
                # VALIDACIÓN
                # -------------------------------------------------

                if not title:
                    raise ProductFetchError(
                        "No se pudo obtener el nombre del producto "
                        "de 1688."
                    )

                if not price:
                    raise ProductFetchError(
                        "No se pudo obtener el precio del producto "
                        "de 1688."
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
