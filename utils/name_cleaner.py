"""Limpieza y reconstrucción de nombres de productos."""

import re

try:
    import wordninja

    _WORDNINJA_AVAILABLE = True
except ImportError:
    _WORDNINJA_AVAILABLE = False


# Marcas conocidas.
BRANDS = {
    "MAISON MARGIELA": ["maisonmargiela", "margiela", "mm6"],
    "STONE ISLAND": ["stoneisland"],
    "THE NORTH FACE": ["thenorthface", "northface"],
    "CHROME HEARTS": ["chromehearts"],
    "OFF-WHITE": ["offwhite"],
    "RICK OWENS": ["rickowens"],
    "BALENCIAGA": ["balenciaga"],
    "LOUIS VUITTON": ["louisvuitton"],
    "GUCCI": ["gucci"],
    "PRADA": ["prada"],
    "SUPREME": ["supreme"],
    "NIKE": ["nike"],
    "ADIDAS": ["adidas"],
    "NEW BALANCE": ["newbalance"],
    "ACNE STUDIOS": ["acnestudios"],
    "FEAR OF GOD": ["fearofgod", "essentials"],
    "CELINE": ["celine"],
    "BOTTEGA VENETA": ["bottegaveneta"],
    "VETEMENTS": ["vetements"],
    "AMIRI": ["amiri"],
    "BAPE": ["bape", "abathingape"],
}


# Palabras habituales que pueden venir pegadas en los títulos.
COMMON_WORDS = [
    "oversized",
    "longsleeve",
    "shortsleeve",
    "tshirt",
    "shirt",
    "bottoming",
    "hoodie",
    "sweater",
    "jacket",
    "pants",
    "trousers",
    "jeans",
    "shorts",
    "cotton",
    "weight",
    "wool",
    "leather",
    "denim",
    "knit",
    "zipper",
    "zip",
    "crewneck",
    "neck",
    "polo",
    "vest",
    "cardigan",
    "coat",
    "windbreaker",
    "tracksuit",
    "sneakers",
    "shoes",
    "boots",
    "bag",
    "cap",
    "hat",
]

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "new",
    "hot",
    "sale",
    "item",
    "product",
    "style",
}

_BRACKET_RE = re.compile(r"[【\[\(][^】\)\]]*[】\)\]]")
_NON_WORD_SEP_RE = re.compile(r"[-_/|]+")
_MULTI_SPACE_RE = re.compile(r"\s+")

_TRAILING_CODE_RE = re.compile(
    r"([0-9]+[A-Za-z]+[0-9]*|[A-Za-z]+[0-9]+[A-Za-z]*)$"
)

_CODE_TOKEN_RE = re.compile(
    r"^[A-Za-z]{1,4}\d{2,5}[A-Za-z]{0,3}$|^\d{1,5}[A-Za-z]{1,4}$"
)

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_LETTER_DIGIT_RE = re.compile(r"(?<=[A-Za-z])(?=\d)")
_DIGIT_LETTER_RE = re.compile(r"(?<=\d)(?=[A-Za-z])")

_MAX_DESCRIPTION_WORDS = 6


def clean_product_name(raw_name: str) -> str:
    """Convierte un nombre basura del proveedor en un nombre legible."""

    if not raw_name or not raw_name.strip():
        return "PRODUCTO"

    # Limpieza inicial.
    text = _BRACKET_RE.sub(" ", raw_name)
    text = _NON_WORD_SEP_RE.sub(" ", text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip()

    # Eliminar códigos internos finales como RR88C.
    text = _strip_trailing_code(text)

    # Separar camelCase:
    # WeightCottonTshirt -> Weight Cotton Tshirt
    text = _CAMEL_BOUNDARY_RE.sub(" ", text)

    # Separar letras y números:
    # Shirt300 -> Shirt 300
    text = _LETTER_DIGIT_RE.sub(" ", text)
    text = _DIGIT_LETTER_RE.sub(" ", text)

    text = _MULTI_SPACE_RE.sub(" ", text).strip()

    # Separar palabras conocidas aunque estén pegadas.
    text = _split_common_words(text)

    compact_lower = re.sub(r"[^a-z0-9]", "", raw_name.lower())

    brand = _detect_brand(compact_lower)
    brand_alias_tokens = _brand_alias_tokens(brand) if brand else set()

    words = []
    seen = set()

    for token in text.split():
        token = token.strip()

        if not token:
            continue

        if len(token) <= 1:
            continue

        if _CODE_TOKEN_RE.match(token):
            continue

        if token.isdigit():
            continue

        low = token.lower()

        if low in _STOPWORDS:
            continue

        if low in brand_alias_tokens:
            continue

        if low in seen:
            continue

        seen.add(low)
        words.append(token)

    description = " ".join(words[:_MAX_DESCRIPTION_WORDS])

    if brand and description:
        final = f"{brand} {description}"
    elif brand:
        final = brand
    elif description:
        final = description
    else:
        final = "PRODUCTO"

    return final.upper()


def _split_common_words(text: str) -> str:
    """Separa palabras habituales que vienen pegadas."""

    result = text

    # Repetimos varias veces para poder separar cadenas como:
    # Weightcottonshirtbottominglongsleeve
    changed = True

    while changed:
        changed = False

        for word in sorted(COMMON_WORDS, key=len, reverse=True):
            pattern = rf"(?i)(?<![A-Za-z])({re.escape(word)})(?![A-Za-z])"

            # Si ya está separado, no hacer nada.
            if re.search(pattern, result):
                continue

            # Buscar la palabra dentro de otra cadena.
            pattern_inside = rf"(?i)([A-Za-z])({re.escape(word)})([A-Za-z])"

            new_result = re.sub(
                pattern_inside,
                r"\1 \2 \3",
                result,
            )

            if new_result != result:
                result = new_result
                changed = True

    return _MULTI_SPACE_RE.sub(" ", result).strip()


def _strip_trailing_code(text: str) -> str:
    match = _TRAILING_CODE_RE.search(text)

    if not match:
        return text

    code = match.group(1)

    if len(code) <= 10:
        return text[:-len(code)]

    return text


def _detect_brand(compact_lower_title: str) -> str:
    for canonical, aliases in BRANDS.items():
        for alias in aliases:
            if alias in compact_lower_title:
                return canonical

    return ""


def _brand_alias_tokens(canonical_brand: str) -> set[str]:
    return {
        word.lower()
        for word in canonical_brand.replace("-", " ").split()
    }
