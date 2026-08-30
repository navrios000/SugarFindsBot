"""Carga y valida la configuración del bot desde variables de entorno."""

import os


_DEFAULT_CNY_EUR_RATE = 0.128


class ConfigError(Exception):
    """Error de configuración."""


class Config:
    def __init__(
        self,
        bot_token: str,
        admin_ids: set[int],
        spreadsheet_url: str,
        sugargoo_member_id: str,
        sugargoo_coupon: str,
        usfans_ref: str,
        usfans_coupon: str,
        cny_eur_rate: float,
    ):
        self.bot_token = bot_token
        self.admin_ids = admin_ids
        self.spreadsheet_url = spreadsheet_url
        self.sugargoo_member_id = sugargoo_member_id
        self.sugargoo_coupon = sugargoo_coupon
        self.usfans_ref = usfans_ref
        self.usfans_coupon = usfans_coupon
        self.cny_eur_rate = cny_eur_rate


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()

    for part in raw.split(","):
        part = part.strip()

        if not part:
            continue

        if not part.lstrip("-").isdigit():
            raise ConfigError(
                f"ADMIN_IDS contiene un valor no numérico: '{part}'"
            )

        ids.add(int(part))

    return ids


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise ConfigError(f"{name} no está definido.")

    return value


def _sanitize_member_id(raw: str) -> str:
    """Elimina un posible 'memberId=' puesto por error."""

    cleaned = raw.strip()

    if cleaned.lower().startswith("memberid="):
        cleaned = cleaned.split("=", 1)[1].strip()

    return cleaned


def _parse_cny_eur_rate(raw: str) -> float:
    raw = raw.strip()

    if not raw:
        return _DEFAULT_CNY_EUR_RATE

    try:
        return float(raw.replace(",", "."))
    except ValueError as e:
        raise ConfigError(
            f"CNY_EUR_RATE debe ser un número "
            f"(recibido: '{raw}')."
        ) from e


def load_config() -> Config:
    """Carga toda la configuración."""

    bot_token = _require("BOT_TOKEN")

    admin_ids = _parse_admin_ids(
        os.getenv("ADMIN_IDS", "")
    )

    if not admin_ids:
        raise ConfigError(
            "ADMIN_IDS no está definido o está vacío."
        )

    spreadsheet_url = _require("SPREADSHEET_URL")

    sugargoo_member_id = _sanitize_member_id(
        _require("SUGARGOO_MEMBER_ID")
    )

    sugargoo_coupon = _require("SUGARGOO_COUPON")

    usfans_ref = _require("USFANS_REF")

    usfans_coupon = _require("USFANS_COUPON")

    cny_eur_rate = _parse_cny_eur_rate(
        os.getenv("CNY_EUR_RATE", "")
    )

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        spreadsheet_url=spreadsheet_url,
        sugargoo_member_id=sugargoo_member_id,
        sugargoo_coupon=sugargoo_coupon,
        usfans_ref=usfans_ref,
        usfans_coupon=usfans_coupon,
        cny_eur_rate=cny_eur_rate,
    )
