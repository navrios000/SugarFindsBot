"""Detector de marcas a partir de nombres e imágenes de productos."""

import asyncio
import base64
import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("sugarfinds")


# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

OPENAI_RETRIES = 3

OPENAI_TIMEOUT = 30

IMAGE_DOWNLOAD_TIMEOUT = 15

# Evita mandar demasiadas peticiones simultáneas a OpenAI.
BRAND_REQUEST_CONCURRENCY = 2

_brand_semaphore = asyncio.Semaphore(
    BRAND_REQUEST_CONCURRENCY
)


# ---------------------------------------------------------------------------
# MARCAS
# ---------------------------------------------------------------------------

KNOWN_BRANDS = [
    "ADIDAS",
    "ALEXANDER MCQUEEN",
    "AMIRI",
    "ARC'TERYX",
    "ASICS",
    "BALENCIAGA",
    "BAPE",
    "BOTTEGA VENETA",
    "BURBERRY",
    "CARHARTT",
    "CELINE",
    "CHANEL",
    "CHROME HEARTS",
    "DIOR",
    "DOLCE & GABBANA",
    "ESSENTIALS",
    "FEAR OF GOD",
    "FOG ESSENTIALS",
    "GIVENCHY",
    "GUCCI",
    "HERMÈS",
    "JORDAN",
    "LACOSTE",
    "LOUIS VUITTON",
    "MAISON MARGIELA",
    "MONCLER",
    "MONCLER GENIUS",
    "NEW BALANCE",
    "NIKE",
    "OFF-WHITE",
    "PALM ANGELS",
    "PRADA",
    "RALPH LAUREN",
    "RICK OWENS",
    "SALOMON",
    "STONE ISLAND",
    "SUPREME",
    "THE NORTH FACE",
    "THOM BROWNE",
    "TRAVIS SCOTT",
    "UNIQLO",
    "VETEMENTS",
    "VERSACE",
    "YEEZY",
]


# ---------------------------------------------------------------------------
# DETECCIÓN POR NOMBRE
# ---------------------------------------------------------------------------

def detect_brand_from_name(name: str) -> str:
    """Detecta una marca conocida a partir del nombre."""

    if not name:
        return ""

    normalized = " ".join(
        name.upper()
        .replace("_", " ")
        .split()
    )

    # Primero marcas completas.
    for brand in sorted(
        KNOWN_BRANDS,
        key=len,
        reverse=True,
    ):

        if brand in normalized:
            return brand

    # Alias habituales.
    aliases = {
        "MM6": "MAISON MARGIELA",
        "MARGIELA": "MAISON MARGIELA",
        "TNF": "THE NORTH FACE",
        "NORTHFACE": "THE NORTH FACE",
        "STONEISLAND": "STONE ISLAND",
        "CHROMEHEARTS": "CHROME HEARTS",
        "RICKOWENS": "RICK OWENS",
        "OFFWHITE": "OFF-WHITE",
        "MONCLER": "MONCLER",
        "ESSENTIALS": "ESSENTIALS",
        "FOG": "FEAR OF GOD",
    }

    compact = normalized.replace(
        " ",
        "",
    )

    for alias, brand in aliases.items():

        if alias in compact:
            return brand

    return ""


# ---------------------------------------------------------------------------
# DETECCIÓN POR IMAGEN
# ---------------------------------------------------------------------------

async def detect_brand_from_image(
    image_url: str,
) -> str:
    """
    Intenta detectar la marca visible en una imagen usando OpenAI Vision.

    Las operaciones bloqueantes de urllib se ejecutan en un thread
    para no bloquear el event loop del bot.
    """

    api_key = os.environ.get(
        "OPENAI_API_KEY"
    )

    if not api_key or not image_url:
        return ""

    try:

        # ---------------------------------------------------------------
        # DESCARGA DE IMAGEN FUERA DEL EVENT LOOP
        # ---------------------------------------------------------------

        image_data = await asyncio.to_thread(
            _download_image,
            image_url,
        )

        if not image_data:
            return ""

        image_b64 = base64.b64encode(
            image_data
        ).decode("ascii")

        payload = {
            "model": "gpt-4.1-mini",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Identify the clothing or fashion brand "
                                "visible in this product image. "
                                "Look carefully for logos, text, symbols "
                                "and distinctive branding. "
                                "Return ONLY the brand name if you are "
                                "confident. "
                                "If there is no recognizable brand, "
                                "return exactly NONE. "
                                "Do not guess."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": (
                                "data:image/jpeg;base64,"
                                f"{image_b64}"
                            ),
                        },
                    ],
                }
            ],
            "max_output_tokens": 30,
        }

        # ---------------------------------------------------------------
        # LIMITAR PETICIONES SIMULTÁNEAS
        # ---------------------------------------------------------------

        async with _brand_semaphore:

            result = await _openai_request_async(
                api_key,
                payload,
            )

        # ---------------------------------------------------------------
        # EXTRAER RESPUESTA
        # ---------------------------------------------------------------

        brand = (
            _extract_response_text(result)
            .strip()
            .upper()
        )

        if not brand or brand == "NONE":
            return ""

        # Si devuelve una marca conocida,
        # usamos el nombre oficial.
        detected = detect_brand_from_name(
            brand
        )

        if detected:
            return detected

        # Marca no incluida en KNOWN_BRANDS.
        if (
            len(brand) <= 40
            and "\n" not in brand
        ):
            return brand

        return ""

    except HTTPError as e:

        logger.warning(
            "OpenAI devolvió HTTP %s "
            "detectando marca.",
            e.code,
        )

        return ""

    except Exception:

        logger.exception(
            "Error detectando marca desde imagen"
        )

        return ""


# ---------------------------------------------------------------------------
# DESCARGA DE IMAGEN
# ---------------------------------------------------------------------------

def _download_image(
    url: str,
) -> bytes:
    """Descarga una imagen con User-Agent de navegador."""

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 "
                "Chrome/131.0 Safari/537.36"
            )
        },
    )

    with urlopen(
        request,
        timeout=IMAGE_DOWNLOAD_TIMEOUT,
    ) as response:

        return response.read()


# ---------------------------------------------------------------------------
# OPENAI ASYNC WRAPPER
# ---------------------------------------------------------------------------

async def _openai_request_async(
    api_key: str,
    payload: dict,
) -> dict:
    """
    Ejecuta la petición bloqueante a OpenAI fuera del event loop.

    Incluye reintentos específicos para 429.
    """

    last_error = None

    for attempt in range(
        1,
        OPENAI_RETRIES + 1,
    ):

        try:

            logger.info(
                "Petición de detección de marca "
                "a OpenAI (intento %d/%d)",
                attempt,
                OPENAI_RETRIES,
            )

            return await asyncio.to_thread(
                _openai_request,
                api_key,
                payload,
            )

        except HTTPError as e:

            last_error = e

            # -----------------------------------------------------------
            # RATE LIMIT
            # -----------------------------------------------------------

            if e.code == 429:

                if attempt >= OPENAI_RETRIES:

                    logger.warning(
                        "OpenAI sigue devolviendo 429 "
                        "después de %d intentos.",
                        OPENAI_RETRIES,
                    )

                    raise

                retry_after = e.headers.get(
                    "Retry-After"
                )

                if retry_after:

                    try:
                        wait_seconds = float(
                            retry_after
                        )

                    except ValueError:
                        wait_seconds = (
                            5 * attempt
                        )

                else:

                    wait_seconds = (
                        5 * attempt
                    )

                # Evitamos esperas absurdamente largas.
                wait_seconds = min(
                    wait_seconds,
                    60,
                )

                logger.warning(
                    "OpenAI HTTP 429. "
                    "Esperando %.1fs antes de reintentar...",
                    wait_seconds,
                )

                await asyncio.sleep(
                    wait_seconds
                )

                continue

            # -----------------------------------------------------------
            # OTROS ERRORES HTTP
            # -----------------------------------------------------------

            logger.warning(
                "OpenAI devolvió HTTP %s.",
                e.code,
            )

            raise

        except (TimeoutError, URLError) as e:

            last_error = e

            if attempt >= OPENAI_RETRIES:
                raise

            wait_seconds = (
                3 * attempt
            )

            logger.warning(
                "Error de conexión con OpenAI: %s. "
                "Reintentando en %ss...",
                e,
                wait_seconds,
            )

            await asyncio.sleep(
                wait_seconds
            )

    if last_error:
        raise last_error

    raise RuntimeError(
        "No se pudo completar la petición a OpenAI."
    )


# ---------------------------------------------------------------------------
# PETICIÓN OPENAI
# ---------------------------------------------------------------------------

def _openai_request(
    api_key: str,
    payload: dict,
) -> dict:
    """Hace una petición directa a la Responses API de OpenAI."""

    body = json.dumps(
        payload
    ).encode("utf-8")

    request = Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": (
                f"Bearer {api_key}"
            ),
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(
        request,
        timeout=OPENAI_TIMEOUT,
    ) as response:

        return json.loads(
            response.read().decode(
                "utf-8"
            )
        )


# ---------------------------------------------------------------------------
# EXTRAER TEXTO
# ---------------------------------------------------------------------------

def _extract_response_text(
    result: dict,
) -> str:
    """Extrae el texto de la Responses API."""

    if isinstance(
        result.get("output_text"),
        str,
    ):

        return result["output_text"]

    output = result.get(
        "output",
        [],
    )

    for item in output:

        for content in item.get(
            "content",
            [],
        ):

            if content.get(
                "type"
            ) == "output_text":

                return content.get(
                    "text",
                    "",
                )

    return ""
