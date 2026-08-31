
import asyncio

from playwright.async_api import async_playwright


TAOBAO_URL = "https://login.taobao.com/"


async def main():
    async with async_playwright() as p:

        context = await p.chromium.launch_persistent_context(
            "taobao_profile",
            headless=False,
            viewport={
                "width": 1366,
                "height": 900,
            },
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

        page = context.pages[0] if context.pages else await context.new_page()

        print("")
        print("========================================")
        print("        LOGIN TAOBAO")
        print("========================================")
        print("")
        print("Se ha abierto Taobao.")
        print("Inicia sesión MANUALMENTE en la ventana.")
        print("")
        print("Cuando hayas terminado, vuelve aquí.")
        print("NO cierres la ventana del navegador.")
        print("")

        await page.goto(
            TAOBAO_URL,
            wait_until="domcontentloaded",
            timeout=45000,
        )

        input(
            "Pulsa ENTER aquí cuando hayas iniciado sesión..."
        )

        print("")
        print("Comprobando sesión...")

        await page.goto(
            "https://item.taobao.com/item.htm?id=1016302543179",
            wait_until="domcontentloaded",
            timeout=45000,
        )

        await page.wait_for_timeout(7000)

        print("")
        print("URL FINAL:")
        print(page.url)

        print("")
        print("TÍTULO:")
        print(await page.title())

        print("")
        print("La ventana seguirá abierta.")
        print("Si el producto se ve correctamente, la sesión")
        print("se ha guardado en ./taobao_profile/")
        print("")

        input(
            "Pulsa ENTER para cerrar el navegador..."
        )

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())


