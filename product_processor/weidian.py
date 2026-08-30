"""Adaptador de Weidian.

Obtiene nombre, precio e imágenes de un producto de Weidian
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


def _normalise_url(url: str) -> str:
    """Normaliza la URL de Weidian."""

    url = url.strip()

    if not url:
        return ""

    parsed = urlparse(url)

    if not parsed.scheme:
        return "https://" + url

    return url


def _clean_text(value: str) -> str:
    """Limpia texto obtenido de Weidian."""

    if not value:
        return ""

    return re.sub(r"\s+", " ", value).strip()


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

    url = url.strip()

    if url.startswith("//"):
        url = "https:" + url

    return url.split("?")[0]


def _is_product_image(url: str) -> bool:
    """Comprueba si una URL parece corresponder a una imagen real."""

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
        "seller",
        "shop",
    )

    if any(word in lowered for word in junk):
        return False

    return True


def _deduplicate_images(images: list[str]) -> list[str]:
    """Elimina imágenes duplicadas y limita la cantidad."""

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


async def _get_meta_content(page, property_name: str) -> str:
    """Obtiene el contenido de una etiqueta meta."""

    try:

        locator = page.locator(
            f'meta[property="{property_name}"]'
        ).first

        if await locator.count():

            value = await locator.get_attribute(
                "content"
            )

            if value:
                return _clean_text(value)

    except Exception:
        pass

    return ""


async def _extract_title(page) -> str:
    """Extrae el nombre del producto."""

    # 1. Open Graph
    title = await _get_meta_content(
        page,
        "og:title",
    )

    if title:
        return title

    # 2. Meta title / description
    for selector in (
        'meta[name="title"]',
        'meta[name="description"]',
    ):

        try:

            locator = page.locator(selector).first

            if await locator.count():

                value = await locator.get_attribute(
                    "content"
                )

                if value:

                    value = _clean_text(value)

                    if value:
                        return value

        except Exception:
            continue

    # 3. H1
    try:

        h1 = page.locator("h1").first

        if await h1.count():

            value = await h1.inner_text(
                timeout=5000
            )

            value = _clean_text(value)

            if value:
                return value

    except Exception:
        pass

    # 4. Título HTML
    try:

        value = _clean_text(
            await page.title()
        )

        lowered = value.lower()

        if value and not any(
            word in lowered
            for word in (
                "login",
                "sign in",
                "error",
            )
        ):
            return value

    except Exception:
        pass

    return ""


async def _extract_price(page) -> str:
    """Extrae el precio del producto."""

    # Open Graph
    price = await _get_meta_content(
        page,
        "product:price:amount",
    )

    price = _clean_price(price)

    if price:
        return price

    # Selectores de precio
    selectors = [
        '[class*="Price--"]',
        '[class*="price--"]',
        '[class*="Price"]',
        '[class*="price"]',
    ]

    for selector in selectors:

        try:

            locator = page.locator(selector)

            count = await locator.count()

            for index in range(min(count, 20)):

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

    # Buscar patrones en el HTML
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
    """Extrae imágenes del producto."""

    images: list[str] = []

    # Open Graph
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

    # Imágenes del DOM
    try:

        image_elements = page.locator("img")

        count = await image_elements.count()

        for index in range(min(count, 100)):

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

    images = _deduplicate_images(images)

    # -------------------------------------------------
    # WEIDIAN
    # -------------------------------------------------
    #
    # Las últimas 4 imágenes suelen ser imágenes
    # que no queremos publicar.
    #
    # Si hay 4 o menos, conservamos todas para
    # asegurarnos de que siempre haya fotos.
    #

    if len(images) > 4:
        images = images[:-4]

    return images


async def fetch(product_url: str) -> ProductData:
    """Obtiene los datos de un producto de Weidian."""

    product_url = _normalise_url(product_url)

    if not product_url:
        raise ProductFetchError(
            "La URL de Weidian está vacía."
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

            # Bloqueamos recursos innecesarios.
            async def handle_route(route):

                resource_type = (
                    route.request.resource_type
                )

                if resource_type in {
                    "font",
                    "media",
                    "websocket",
                }:

                    await route.abort()

                else:

                    await route.continue_()

            await page.route(
                "**/*",
                handle_route,
            )

            try:

                await page.goto(
                    product_url,
                    wait_until="domcontentloaded",
                    timeout=_PAGE_TIMEOUT,
                )

                # Esperamos a que cargue el contenido dinámico.
                await page.wait_for_timeout(3000)

                current_url = page.url.lower()

                # -------------------------------------------------
                # DETECTAR LOGIN
                # -------------------------------------------------

                if (
                    "login" in current_url
                    or "passport" in current_url
                ):

                    raise ProductFetchError(
                        "Weidian redirigió a una página "
                        "de login."
                    )

                # -------------------------------------------------
                # DETECTAR BLOQUEO / VERIFICACIÓN
                # -------------------------------------------------

                page_text = ""

                try:

                    page_text = (
                        await page.locator(
                            "body"
                        ).inner_text(
                            timeout=5000
                        )
                    ).lower()

                except Exception:
                    pass

                blocked_words = (
                    "captcha",
                    "verify",
                    "验证",
                    "安全验证",
                    "robot",
                    "人机",
                )

                if any(
                    word in page_text
                    for word in blocked_words
                ):

                    raise ProductFetchError(
                        "Weidian mostró una pantalla "
                        "de verificación/anti-bot."
                    )

                # -------------------------------------------------
                # EXTRAER DATOS
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
                        "Weidian no permitió obtener "
                        "el nombre del producto."
                    )

                if not price:

                    raise ProductFetchError(
                        "Weidian no permitió obtener "
                        "el precio del producto."
                    )

                return ProductData(
                    source_url=product_url,
                    platform="weidian",
                    name=title,
                    price=f"¥{price}",
                    images=images,
                )

            finally:

                await context.close()
                await browser.close()

    except PlaywrightTimeoutError as e:

        raise ProductFetchError(
            "Weidian tardó demasiado en responder."
        ) from e

    except ProductFetchError:
        raise

    except Exception as e:

        raise ProductFetchError(
            f"Error al obtener el producto de Weidian: {e}"
        ) from e
