"""Generación de enlaces de afiliado.

Separado a propósito del scraping: este módulo solo construye texto
(URLs), nunca hace peticiones de red. Así se puede testear sin
conexión y reutilizar para cualquier plataforma origen.
"""

from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


def build_sugargoo_url(product_url: str, member_id: str) -> str:
    """Construye el enlace de SugarGoo con memberId.

    Comprobado manualmente (inspect_sugargoo.py): SugarGoo espera el
    `productLink` con DOBLE URL-encoding, no uno solo. Ejemplo
    verificado:

        producto:  https://weidian.com/item.html?itemID=7805672623
        resultado: https://www.sugargoo.com/products?productLink=
                   https%253A%252F%252Fweidian.com%252Fitem.html%253FitemID%253D7805672623
                   &memberId=1130639351717008620
    """
    encoded_once = quote(product_url, safe="")
    encoded_twice = quote(encoded_once, safe="")
    return f"https://www.sugargoo.com/products?productLink={encoded_twice}&memberId={member_id}"


def build_usfans_url(product_url: str, ref: str) -> str:
    """Construye el enlace de producto de USFans con tu referencia (`ref`).

    IMPORTANTE: `ref` es la referencia de afiliado (p.ej. "M3XSLC"),
    NO el código de cupón — son datos distintos (ver Config.usfans_ref
    vs Config.usfans_coupon).

    Comprobado manualmente que un link de producto válido es, p.ej.:
        https://usfans.com/product/3/7782518286?ref=M3XSLC

    No se concatena "?ref=..." a ciegas: se parsea el query string
    existente y se añade/reemplaza el parámetro `ref` con urlencode,
    de forma que el resultado use "?" o "&" correctamente según si la
    URL ya trae otros parámetros:
        sin query:        https://usfans.com/product/3/7782518286
                        -> https://usfans.com/product/3/7782518286?ref=M3XSLC
        con otro query:    https://usfans.com/product/3/7782518286?color=red
                        -> https://usfans.com/product/3/7782518286?color=red&ref=M3XSLC
        con ref distinto:  https://usfans.com/product/3/7782518286?ref=OTRO
                        -> https://usfans.com/product/3/7782518286?ref=M3XSLC
                           (nuestra referencia reemplaza a cualquier otra que ya trajera el link)
    """
    parsed = urlsplit(product_url)

    query_params = [
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "ref"
    ]
    query_params.append(("ref", ref))

    new_query = urlencode(query_params)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))
