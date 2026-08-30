"""Limpieza y reconstrucción del nombre de producto."""

import re

try:
    import wordninja

    _WORDNINJA_AVAILABLE = True
except ImportError:
    _WORDNINJA_AVAILABLE = False


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
_WORDNINJA_MIN_LEN = 10


def clean_product_name(raw_name: str) -> str:
    if not raw_name or not raw_name.strip():
        return ""

    text = _BRACKET_RE.sub(" ", raw_name)
    text = _NON_WORD_SEP_RE.sub(" ", text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip()

    text = _strip_trailing_code(text)

    text = _CAMEL_BOUNDARY_RE.sub(" ", text)
    text = _LETTER_DIGIT_RE.sub(" ", text)
    text = _DIGIT_LETTER_RE.sub(" ", text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip()

    compact_lower = re.sub(r"[^a-z0-9]", "", raw_name.lower())

    brand = _detect_brand(compact_lower)
    brand_alias_tokens = _brand_alias_tokens(brand) if brand else set()

    words = []
    seen = set()

    for token in text.split(" "):
        for sub_token in _maybe_split_lowercase_run(token):
            sub_token = sub_token.strip()

            if not sub_token or len(sub_token) <= 1:
                continue

            if _CODE_TOKEN_RE.match(sub_token):
                continue

            if sub_token.isdigit():
                continue

            low = sub_token.lower()

            if low in _STOPWORDS:
                continue

            if low in brand_alias_tokens:
                continue

            if low in seen:
                continue

            seen.add(low)
            words.append(sub_token)

    description = " ".join(words[:_MAX_DESCRIPTION_WORDS])

    if brand and description:
        final = f"{brand} {description}"
    elif brand:
        final = brand
    elif description:
        final = description
    else:
        final = _MULTI_SPACE_RE.sub(" ", raw_name).strip() or "PRODUCTO"

    return final.upper()


def _strip_trailing_code(text: str) -> str:
    match = _TRAILING_CODE_RE.search(text)

    if not match:
        return text

    code = match.group(1)

    if len(code) <= 10:
        return text[:-len(code)]

    return text


def _maybe_split_lowercase_run(token: str) -> list[str]:
    if (
        _WORDNINJA_AVAILABLE
        and len(token) > _WORDNINJA_MIN_LEN
        and token.isalpha()
        and token.islower()
    ):
        parts = wordninja.split(token)

        if len(parts) > 1:
            return parts

    return [token]


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
