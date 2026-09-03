"""Script de apoyo para verificar cómo responde Weidian sin sesión
iniciada — el equivalente a inspect_sugargoo.py, pero para Weidian.

Uso:   
    python inspect_weidian.py "https://weidian.com/item.html?itemID=XXXXX"

Guarda el HTML crudo en weidian_page.html para poder revisar la
estructura real y ajustar product_processor/weidian.py si hace falta.

Usa solo la librería estándar (urllib), sin dependencias extra, para
que lo puedas ejecutar en tu Mac sin instalar nada nuevo.
"""

import sys
import urllib.request

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def main():
    if len(sys.argv) < 2:
        print('Uso: python inspect_weidian.py "https://weidian.com/item.html?itemID=XXXXX"')
        sys.exit(1)

    url = sys.argv[1]
    print(f"Pidiendo {url} ...")

    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        status = resp.status
        html = resp.read().decode("utf-8", errors="replace")

    print(f"Status: {status}")

    with open("weidian_page.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Guardado en weidian_page.html ({len(html)} caracteres)")
    print("Súbelo al chat si el nombre/precio/fotos no salen bien en el FIND.")


if __name__ == "__main__":
    main()
