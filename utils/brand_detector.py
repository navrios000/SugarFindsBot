
"""Detector de marcas a partir de nombres e imágenes de productos."""

import base64
import json
import logging
import os
from urllib.request import Request, urlopen

logger = logging.getLogger("sugarfinds")


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


def detect_brand_from_name(name: str) -> str:
    """Detecta una marca conocida a partir del nombre."""

    if not name:
        return ""

    normalized = " ".join(
        name.upper().replace("_", " ").split()
    )

    # Primero marcas completas.
    for brand in sorted(KNOWN_BRANDS, key=len, reverse=True):
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

    compact = normalized.replace(" ", "")

    for alias, brand in aliases.items():
        if alias in compact:
            return brand

    return ""


async def detect_brand_from_image(image_url: str) -> str:
    """
    Intenta detectar la marca visible en una imagen usando OpenAI Vision.

    Si no hay API key, la imagen no se puede analizar y devuelve "".
    """

    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key or not image_url:
        return ""

    try:
        image_data = _download_image(image_url)

        if not image_data:
            return ""

        image_b64 = base64.b64encode(image_data).decode("ascii")

        payload = {
            "model": "gpt-4.1-mini",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Identify the clothing or fashion brand visible "
                                "in this product image. Look carefully for logos, "
                                "text, symbols and distinctive branding. "
                                "Return ONLY the brand name if you are confident. "
                                "If there is no recognizable brand, return exactly "
                                "NONE. Do not guess."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": (
                                f"data:image/jpeg;base64,{image_b64}"
                            ),
                        },
                    ],
                }
            ],
            "max_output_tokens": 30,
        }

        result = _openai_request(api_key, payload)

        brand = _extract_response_text(result).strip().upper()

        if not brand or brand == "NONE":
            return ""

        # Si devuelve una marca conocida, usamos el nombre oficial.
        detected = detect_brand_from_name(brand)

        if detected:
            return detected

        # Si devuelve otra marca no incluida en nuestra lista,
        # aceptamos únicamente una respuesta corta.
        if len(brand) <= 40 and "\n" not in brand:
            return brand

        return ""

    except Exception:
        logger.exception(
            "Error detectando marca desde imagen"
        )
        return ""


def _download_image(url: str) -> bytes:
    """Descarga una imagen con User-Agent de navegador."""

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
            )
        },
    )

    with urlopen(request, timeout=15) as response:
        return response.read()


def _openai_request(api_key: str, payload: dict) -> dict:
    """Hace una petición directa a la Responses API de OpenAI."""

    body = json.dumps(payload).encode("utf-8")

    request = Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(request, timeout=30) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def _extract_response_text(result: dict) -> str:
    """Extrae el texto de la Responses API."""

    if isinstance(result.get("output_text"), str):
        return result["output_text"]

    output = result.get("output", [])

    for item in output:
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text", "")

    return ""

