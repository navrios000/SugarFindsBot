
"""Adaptador de Taobao.

Obtiene nombre, precio e imágenes de un producto de Taobao
mediante Playwright.

El adaptador intenta primero obtener los datos estructurados que
Taobao deja en la página y después utiliza el DOM como respaldo.
"""

import json
import re
from urllib.parse import urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from product_processor.base import ProductFetchError
from utils.product_data import ProductData


_MAX_IMAGES = 9
_PAGE_TIMEOUT = 45000

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _normalise_url(url: str) -> str:
    """Normaliza la URL de Taobao."""

    url = (url or "").strip()

    if not url:
        return ""

    parsed = urlparse(url)

    if not parsed.scheme:
        return "https://" + url

    return url


def _clean_text(value: str) -> str:
    """Limpia texto."""

    if not value:
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()


def _clean_price(value: str) -> str:
    """Normaliza un precio."""

    if value is None:
        return ""

    value = str(value).strip()

    if not value:
        return ""

    # Elimina símbolos monetarios y espacios.
    value = value.replace("¥", "")
    value = value.replace("￥", "")
    value = value.replace("RMB", "")
    value = value.replace("元", "")
    value = value.replace(",", ".")

    # Evitar números claramente ajenos al precio.
    match = re.search(r"\d+(?:\.\d{1,2})?", value)

    if not match:
        return ""

    try:
        number = float(match.group(0))

        # Precios absurdamente grandes suelen ser IDs u otros datos.
        if number <= 0 or number > 100000:
            return ""

        # Evitar cosas como 1016302543179.
        if len(match.group(0).split(".")[0]) > 5:
            return ""

    except ValueError:
        return ""

    return match.group(0)


def _clean_image_url(url: str) -> str:
    """Normaliza una URL de imagen."""

    if not url:
        return ""

    url = str(url).strip()

    if url.startswith("//"):
        url = "https:" + url

    # Algunas respuestas JSON contienen escapes.
    url = url.replace("\\/", "/")

    # Quitar parámetros de tracking.
    url = url.split("?")[0]

    return url


def _is_product_image(url: str) -> bool:
    """Determina si una URL parece una imagen de producto."""

    if not url:
        return False

    lowered = url.lower()

    if not lowered.startswith(("http://", "https://")):
        return False

    valid_domains = (
        "alicdn.com",
        "taobao.com",
        "tbcdn.cn",
        "tmall.com",
    )

    if not any(domain in lowered for domain in valid_domains):
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
        "default",
    )

    if any(word in lowered for word in junk):
        return False

    return True


def _deduplicate_images(images: list[str]) -> list[str]:
    """Elimina duplicados y limita el número de imágenes."""

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


async def _get_meta_content(page, selector: str) -> str:
    """Obtiene el content de una meta."""

    try:
        locator = page.locator(selector).first

        if await locator.count():
            value = await locator.get_attribute("content")

            if value:
                return _clean_text(value)

    except Exception:
        pass

    return ""


async def _extract_title(page) -> str:
    """Extrae el nombre del producto."""

    # Open Graph.
    for selector in (
        'meta[property="og:title"]',
        'meta[name="title"]',
    ):
        value = await _get_meta_content(page, selector)

        if value:
            return value

    # JSON-LD.
    try:
        scripts = page.locator(
            'script[type="application/ld+json"]'
        )

        count = await scripts.count()

        for index in range(min(count, 20)):
            text = await scripts.nth(index).text_content()

            if not text:
                continue

            try:
                data = json.loads(text)

            except Exception:
                continue

            objects = data if isinstance(data, list) else [data]

            for obj in objects:
                if not isinstance(obj, dict):
                    continue

                name = _clean_text(obj.get("name", ""))

                if name:
                    return name

    except Exception:
        pass

    # Selectores DOM.
    for selector in (
        "h1",
        '[class*="title"]',
        '[class*="Title"]',
    ):
        try:
            locator = page.locator(selector)

            count = await locator.count()

            for index in range(min(count, 10)):
                value = _clean_text(
                    await locator.nth(index).inner_text(
                        timeout=2000
                    )
                )

                if value and len(value) >= 3:
                    return value

        except Exception:
            continue

    # Título HTML.
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
                "404",
            )
        ):
            return value

    except Exception:
        pass

    return ""


def _price_from_json_object(data) -> str:
    """Busca recursivamente un precio dentro de JSON."""

    if isinstance(data, dict):

        # Preferimos claves que realmente representan precio.
        preferred_keys = (
            "currentPrice",
            "salePrice",
            "discountPrice",
            "price",
            "minPrice",
            "maxPrice",
        )

        for key in preferred_keys:
            if key in data:
                value = _clean_price(data[key])

                if value:
                    return value

        for value in data.values():
            result = _price_from_json_object(value)

            if result:
                return result

    elif isinstance(data, list):

        for item in data:
            result = _price_from_json_object(item)

            if result:
                return result

    return ""


async def _extract_price_from_json(page) -> str:
    """Busca el precio en JSON-LD y scripts de la página."""

    # JSON-LD.
    try:
        scripts = page.locator(
            'script[type="application/ld+json"]'
        )

        count = await scripts.count()

        for index in range(min(count, 20)):

            text = await scripts.nth(index).text_content()

            if not text:
                continue

            try:
                data = json.loads(text)

            except Exception:
                continue

            price = _price_from_json_object(data)

            if price:
                return price

    except Exception:
        pass

    # Scripts de Taobao.
    try:
        scripts = page.locator("script")

        count = await scripts.count()

        for index in range(min(count, 150)):

            text = await scripts.nth(index).text_content()

            if not text:
                continue

            # Solo analizar scripts que parecen contener precios.
            if not re.search(
                r"currentPrice|salePrice|discountPrice|price",
                text,
                re.IGNORECASE,
            ):
                continue

            patterns = (
                r'"currentPrice"\s*:\s*"([^"]+)"',
                r'"currentPrice"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
                r'"salePrice"\s*:\s*"([^"]+)"',
                r'"salePrice"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
                r'"discountPrice"\s*:\s*"([^"]+)"',
                r'"discountPrice"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
                r'"price"\s*:\s*"([^"]+)"',
                r'"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
            )

            for pattern in patterns:

                match = re.search(
                    pattern,
                    text,
                    re.IGNORECASE,
                )

                if not match:
                    continue

                price = _clean_price(match.group(1))

                if price:
                    return price

    except Exception:
        pass

    return ""


async def _extract_price_from_meta(page) -> str:
    """Extrae el precio desde meta tags."""

    selectors = (
        'meta[itemprop="price"]',
        'meta[property="product:price:amount"]',
        'meta[property="product:price"]',
        'meta[name="price"]',
    )

    for selector in selectors:

        try:
            locator = page.locator(selector)

            count = await locator.count()

            for index in range(min(count, 20)):

                value = await locator.nth(index).get_attribute(
                    "content"
                )

                price = _clean_price(value or "")

                if price:
                    return price

        except Exception:
            continue

    return ""


async def _extract_price_from_dom(page) -> str:
    """Busca el precio visible en el DOM."""

    selectors = (
        '[itemprop="price"]',
        '[data-testid*="price"]',
        '[class*="Price--"]',
        '[class*="price--"]',
        '[class*="PriceText"]',
        '[class*="priceText"]',
    )

    for selector in selectors:

        try:
            locator = page.locator(selector)

            count = await locator.count()

            for index in range(min(count, 30)):

                element = locator.nth(index)

                value = await element.get_attribute("content")

                if not value:
                    value = await element.get_attribute("data-price")

                if not value:
                    try:
                        value = await element.inner_text(
                            timeout=1500
                        )
                    except Exception:
                        value = ""

                price = _clean_price(value or "")

                if price:
                    return price

        except Exception:
            continue

    return ""


async def _extract_price(page) -> str:
    """Extrae el precio utilizando varias fuentes."""

    # 1. Meta.
    price = await _extract_price_from_meta(page)

    if price:
        return price

    # 2. JSON.
    price = await _extract_price_from_json(page)

    if price:
        return price

    # 3. DOM.
    price = await _extract_price_from_dom(page)

    if price:
        return price

    return ""


async def _extract_images(page) -> list[str]:
    """Extrae imágenes del producto."""

    images: list[str] = []

    # ---------------------------------------------------------
    # Open Graph
    # ---------------------------------------------------------

    try:
        locator = page.locator(
            'meta[property="og:image"]'
        )

        count = await locator.count()

        for index in range(count):
            value = await locator.nth(index).get_attribute(
                "content"
            )

            if value:
                images.append(value)

    except Exception:
        pass

    # ---------------------------------------------------------
    # JSON-LD
    # ---------------------------------------------------------

    try:
        scripts = page.locator(
            'script[type="application/ld+json"]'
        )

        count = await scripts.count()

        for index in range(min(count, 20)):

            text = await scripts.nth(index).text_content()

            if not text:
                continue

            try:
                data = json.loads(text)

            except Exception:
                continue

            objects = data if isinstance(data, list) else [data]

            for obj in objects:

                if not isinstance(obj, dict):
                    continue

                image = obj.get("image")

                if isinstance(image, str):
                    images.append(image)

                elif isinstance(image, list):
                    images.extend(
                        item
                        for item in image
                        if isinstance(item, str)
                    )

    except Exception:
        pass

    # ---------------------------------------------------------
    # DOM
    # ---------------------------------------------------------

    try:
        locator = page.locator("img")

        count = await locator.count()

        for index in range(min(count, 150)):

            element = locator.nth(index)

            for attribute in (
                "src",
                "data-src",
                "data-lazy-src",
                "data-original",
                "data-ks-lazyload",
            ):

                value = await element.get_attribute(attribute)

                if value:
                    images.append(value)
                    break

    except Exception:
        pass

    # ---------------------------------------------------------
    # HTML
    # ---------------------------------------------------------

    # Taobao a veces deja URLs de imágenes en atributos o scripts
    # aunque todavía no estén representadas como <img>.
    try:
        html = await page.content()

        found = re.findall(
            r'https?:?\\?/\\?/[^"\'\\s<>]+?\.(?:jpg|jpeg|png|webp)',
            html,
            re.IGNORECASE,
        )

        images.extend(found)

    except Exception:
        pass

    return _deduplicate_images(images)


async def _detect_block(page) -> str:
    """Detecta bloqueos evidentes."""

    current_url = page.url.lower()

    if (
        "login.taobao.com" in current_url
        or "login.tmall.com" in current_url
    ):
        return "Taobao redirigió a la página de login."

    try:
        text = await page.locator("body").inner_text(
            timeout=5000
        )

        text = text.lower()

    except Exception:
        text = ""

    # Solo palabras muy claras.
    blocked_groups = (
        (
            "captcha",
            "验证码",
            "安全验证",
            "滑块验证",
        ),
        (
            "人机验证",
            "请完成验证",
            "访问异常",
        ),
    )

    for group in blocked_groups:

        if any(word.lower() in text for word in group):

            return (
                "Taobao mostró una pantalla de "
                "verificación/anti-bot."
            )

    return ""


async def _debug_taobao(
    page,
    title: str,
    price: str,
    images: list[str],
) -> None:
    """Información de diagnóstico para Render."""

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

    print("")
    print("IMAGES:")
    print(len(images))

    for image in images:
        print(image)

    try:
        body_text = await page.locator("body").inner_text(
            timeout=5000
        )

        print("")
        print("========== BODY TEXT ==========")
        print(body_text[:12000])

    except Exception as e:
        print("")
        print("ERROR BODY TEXT:")
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
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )

            context = await browser.new_context(
                user_agent=_USER_AGENT,
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                viewport={
                    "width": 1366,
                    "height": 900,
                },
                is_mobile=False,
                device_scale_factor=1,
            )

            page = await context.new_page()

            try:

                # -------------------------------------------------
                # CABECERAS
                # -------------------------------------------------

                await page.set_extra_http_headers(
                    {
                        "Accept-Language": (
                            "zh-CN,zh;q=0.9,en;q=0.8"
                        ),
                    }
                )

                # -------------------------------------------------
                # ABRIR TAOBAO
                # -------------------------------------------------

                response = await page.goto(
                    product_url,
                    wait_until="domcontentloaded",
                    timeout=_PAGE_TIMEOUT,
                )

                if response is not None:
                    print(
                        "TAOBAO HTTP STATUS:",
                        response.status,
                    )

                # Dejar que JavaScript termine de construir
                # la página del producto.
                await page.wait_for_timeout(7000)

                # Esperar a que exista algo de contenido.
                try:
                    await page.locator("body").wait_for(
                        timeout=10000
                    )
                except Exception:
                    pass

                # -------------------------------------------------
                # DETECTAR BLOQUEO
                # -------------------------------------------------

                block_reason = await _detect_block(page)

                if block_reason:
                    raise ProductFetchError(
                        block_reason
                    )

                # -------------------------------------------------
                # EXTRAER
                # -------------------------------------------------

                title = await _extract_title(page)

                price = await _extract_price(page)

                images = await _extract_images(page)

                # -------------------------------------------------
                # DEBUG
                # -------------------------------------------------

                await _debug_taobao(
                    page,
                    title,
                    price,
                    images,
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
                # RESULTADO
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


