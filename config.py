"""Carga y valida la configuración del bot desde variables de entorno.

No imprime ni sale del proceso aquí: lanza ConfigError con un mensaje
claro para que bot.py lo capture y lo registre con el logger ya
configurado.
"""

import os


class ConfigError(Exception):
    """Error de configuración (variable de entorno faltante o inválida)."""


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
    ):
        self.bot_token = bot_token
        self.admin_ids = admin_ids
        self.spreadsheet_url = spreadsheet_url
        self.sugargoo_member_id = sugargoo_member_id
        self.sugargoo_coupon = sugargoo_coupon
        self.usfans_ref = usfans_ref  # referencia de afiliado, p.ej. "M3XSLC" — NO es el cupón
        self.usfans_coupon = usfans_coupon


def _parse_admin_ids(raw: str) -> set[int]:
    """Convierte 'id1, id2, id3' en un set de enteros."""
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.lstrip("-").isdigit():
            raise ConfigError(f"ADMIN_IDS contiene un valor no numérico: '{part}'")
        ids.add(int(part))
    return ids


def _require(name: str) -> str:
    """Lee una variable de entorno obligatoria (texto libre, no numérica)."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"{name} no está definido.")
    return value


def load_config() -> Config:
    """Lee y valida toda la configuración. Lanza ConfigError si falta algo."""
    bot_token = _require("BOT_TOKEN")

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    if not admin_ids:
        raise ConfigError("ADMIN_IDS no está definido o está vacío.")

    spreadsheet_url = _require("SPREADSHEET_URL")
    sugargoo_member_id = _require("SUGARGOO_MEMBER_ID")
    sugargoo_coupon = _require("SUGARGOO_COUPON")
    usfans_ref = _require("USFANS_REF")
    usfans_coupon = _require("USFANS_COUPON")

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        spreadsheet_url=spreadsheet_url,
        sugargoo_member_id=sugargoo_member_id,
        sugargoo_coupon=sugargoo_coupon,
        usfans_ref=usfans_ref,
        usfans_coupon=usfans_coupon,
    )
