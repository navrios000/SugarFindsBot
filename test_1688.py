import asyncio

from product_processor.platform_1688 import fetch


URL = "PEGA_AQUI_UN_ENLACE_DE_1688"


async def main():

    try:

        product = await fetch(URL)

        print("\n========== 1688 RESULTADO ==========")

        print("Nombre:", product.name)
        print("Precio:", product.price)
        print("Imágenes:", len(product.images))

        for image in product.images:
            print(image)

    except Exception as e:

        print("\n========== 1688 ERROR ==========")
        print(type(e).__name__)
        print(e)


asyncio.run(main())
