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
_PAGE_TIMEOUT = 30000

_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)


def _normalise_url(url: str) -> str:
    """Normaliza la URL de Taobao."""

    url = url.strip()

    if not url:
        return ""

    parsed = urlparse(url)

    if not parsed.scheme:
        return "https://" + url

    return url


def _clean_text(value: str) -> str:
    """Limpia texto obtenido de Taobao."""

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

    valid_domains = (
        "alicdn.com",
        "taobao.com",
        "tbcdn.cn",
    )

    if not any(domain in lowered for domain in valid_domains):
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
            value = await locator.get_attribute("content")

            if value:
                return _clean_text(value)

    except Exception:
        pass

    return ""


async def _extract_title(page) -> str:
    """Extrae el nombre del producto usando varios métodos."""

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
                value = await locator.get_attribute("content")

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
            value = await h1.inner_text(timeout=5000)
            value = _clean_text(value)

            if value:
                return value

    except Exception:
        pass

    # 4. Título HTML
    try:
        value = _clean_text(await page.title())

        lowered = value.lower()

        if value and not any(
            word in lowered
            for word in (
                "login",
                "sign in",
                "登录",
                "error",
            )
        ):
            return value

    except Exception:
        pass

    return ""


async def _extract_price(page) -> str:
    """Extrae el precio del producto usando varios métodos."""

    # ---------------------------------------------------------
    # 1. Open Graph
    # ---------------------------------------------------------

    price = await _get_meta_content(
        page,
        "product:price:amount",
    )

    price = _clean_price(price)

    if price:
        return price

    # ---------------------------------------------------------
    # 2. Meta tags alternativas
    # ---------------------------------------------------------

    meta_selectors = [
        'meta[itemprop="price"]',
        'meta[name="price"]',
        'meta[property="product:price"]',
        'meta[property="product:price:amount"]',
    ]

    for selector in meta_selectors:

        try:

            locator = page.locator(selector)

            count = await locator.count()

            for index in range(min(count, 10)):

                value = await locator.nth(index).get_attribute(
                    "content"
                )

                cleaned = _clean_price(value or "")

                if cleaned:
                    return cleaned

        except Exception:
            continue

    # ---------------------------------------------------------
    # 3. Selectores de precio
    # ---------------------------------------------------------

    selectors = [
        '[class*="Price--"]',
        '[class*="price--"]',
        '[class*="Price"]',
        '[class*="price"]',
        '[class*="PriceText"]',
        '[class*="priceText"]',
        '[data-testid*="price"]',
        '[data-spm*="price"]',
        '[itemprop="price"]',
    ]

    for selector in selectors:

        try:

            locator = page.locator(selector)

            count = await locator.count()

            for index in range(min(count, 30)):

                element = locator.nth(index)

                # Primero atributo content
                value = await element.get_attribute(
                    "content"
                )

                # Después texto visible
                if not value:
                    try:
                        value = await element.inner_text(
                            timeout=1000
                        )
                    except Exception:
                        value = ""

                cleaned = _clean_price(value or "")

                if cleaned:
                    return cleaned

        except Exception:
            continue

    # ---------------------------------------------------------
    # 4. JSON / JavaScript de la página
    # ---------------------------------------------------------

    try:

        html = await page.content()

        patterns = [

            # "price":"29.99"
            r'"price"\s*:\s*"([\d]+(?:\.[\d]+)?)"',

            # "price":29.99
            r'"price"\s*:\s*([\d]+(?:\.[\d]+)?)',

            # "currentPrice":"29.99"
            r'"currentPrice"\s*:\s*"([\d]+(?:\.[\d]+)?)"',

            # "currentPrice":29.99
            r'"currentPrice"\s*:\s*([\d]+(?:\.[\d]+)?)',

            # "salePrice":"29.99"
            r'"salePrice"\s*:\s*"([\d]+(?:\.[\d]+)?)"',

            # "salePrice":29.99
            r'"salePrice"\s*:\s*([\d]+(?:\.[\d]+)?)',

            # "discountPrice":"29.99"
            r'"discountPrice"\s*:\s*"([\d]+(?:\.[\d]+)?)"',

            # "discountPrice":29.99
            r'"discountPrice"\s*:\s*([\d]+(?:\.[\d]+)?)',
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

    # ---------------------------------------------------------
    # Open Graph
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # Imágenes del DOM
    # ---------------------------------------------------------

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

    return _deduplicate_images(images)


async def _debug_taobao(page, title: str, price: str) -> None:
    """Imprime información útil para diagnosticar Taobao en Render."""

    print("")
    print("========== TAOBAO DEBUG ==========")

    print("URL FINAL:")
    print(page.url)

    print("")
    print("TITLE:")
    print(title)

    print("")
    print("PRICE:")
    print(price)

    # ---------------------------------------------------------
    # Texto visible
    # ---------------------------------------------------------

    try:

        body_text = await page.locator(
            "body"
        ).inner_text(
            timeout=5000
        )

        print("")
        print("========== BODY TEXT ==========")
        print(body_text[:15000])

    except Exception as e:

        print("")
        print("ERROR BODY TEXT:")
        print(e)

    # ---------------------------------------------------------
    # Buscar referencias a precios en HTML
    # ---------------------------------------------------------

    try:

        html = await page.content()

        print("")
        print("========== HTML PRICE MATCHES ==========")

        matches = re.findall(
            r'(?i).{0,150}(?:price|precio|价格|¥|￥).{0,250}',
            html,
        )

        for match in matches[:50]:
            print(match)

    except Exception as e:

        print("")
        print("ERROR HTML DEBUG:")
        print(e)

    print("")
    print("=================================")
    print("")


async def fetch(product_url: str) -> ProductData:
    """Obtiene los datos de un producto de Taobao."""

    product_url = _normalise_url(product_url)

    if not product_url:
        raise ProductFetchError(
            "La URL de Taobao está vacía."
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

            # -------------------------------------------------
            # BLOQUEAR RECURSOS PESADOS
            # -------------------------------------------------

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

                # -------------------------------------------------
                # ABRIR TAOBAO
                # -------------------------------------------------

                await page.goto(
                    product_url,
                    wait_until="domcontentloaded",
                    timeout=_PAGE_TIMEOUT,
                )

                # Esperar contenido dinámico
                await page.wait_for_timeout(5000)

                current_url = page.url.lower()

                # -------------------------------------------------
                # DETECTAR LOGIN
                # -------------------------------------------------

                if (
                    "login.taobao.com" in current_url
                    or "login.tmall.com" in current_url
                ):
                    raise ProductFetchError(
                        "Taobao redirigió a login. "
                        "El producto está bloqueado para acceso "
                        "sin sesión."
                    )

                # -------------------------------------------------
                # DETECTAR CAPTCHA / ANTI-BOT
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
                    "滑块",
                    "异常访问",
                )

                if any(
                    word in page_text
                    for word in blocked_words
                ):
                    raise ProductFetchError(
                        "Taobao mostró una pantalla de "
                        "verificación/anti-bot."
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
                # DEBUG
                # -------------------------------------------------

                await _debug_taobao(
                    page,
                    title,
                    price,
                )

                # -------------------------------------------------
                # VALIDACIÓN
                # -------------------------------------------------

                if not title:
                    raise ProductFetchError(
                        "Taobao no permitió obtener el nombre "
                        "del producto."
                    )

                if not price:
                    raise ProductFetchError(
                        "Taobao no permitió obtener el precio "
                        "del producto."
                    )

                # -------------------------------------------------
                # PRODUCT DATA
                # -------------------------------------------------

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
