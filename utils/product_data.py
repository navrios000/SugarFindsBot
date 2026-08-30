from dataclasses import dataclass, field


@dataclass
class ProductData:
    source_url: str
    platform: str
    name: str
    price: str
    images: list[str] = field(default_factory=list)

    # Datos añadidos antes de publicar el FIND
    spreadsheet_url: str = ""
    sugargoo_url: str = ""
    usfans_url: str = ""
    sugargoo_coupon: str = ""
    usfans_coupon: str = ""
