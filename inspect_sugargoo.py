from playwright.sync_api import sync_playwright

URL = "https://www.sugargoo.com/products?productLink=https%253A%252F%252Fweidian.com%252Fitem.html%253FitemID%253D7805672623&memberId=1130639351717008620"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="Europe/Madrid"
    )

    page = context.new_page()

    print("Abriendo SugarGoo...")

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)

    page.wait_for_timeout(10000)

    print("Título:", page.title())
    print("URL final:", page.url)

    print("========== TEXTO VISIBLE ==========")

    text = page.locator("body").inner_text()
    print(text[:15000])

    print("========== HTML GUARDADO ==========")

    html = page.content()

    with open("sugargoo_page.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("HTML guardado en sugargoo_page.html")

    print("Esperando 20 segundos...")
    page.wait_for_timeout(20000)

    browser.close()
