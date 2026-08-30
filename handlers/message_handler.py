"""Handler de mensajes: detecta enlaces, genera el FIND y lo publica."""

import logging

from telegram import InputMediaPhoto, Update
from telegram.ext import ContextTypes

from product_processor.base import ProductFetchError
from product_processor.dispatcher import UnsupportedPlatformError, process

from utils.affiliate import (
    build_sugargoo_url,
    build_usfans_product_url,
)

from utils.find_formatter import build_find_caption
from utils.link_parser import find_product_link
from utils.pricing import cny_to_eur


logger = logging.getLogger("sugarfinds")


CHANNEL_ID = -1004404116341


def build_message_handler(config):

    async def handle_message(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        message = update.message

        if not message or not message.text:
            return

        user = update.effective_user

        # ─────────────────────────────────────────
        # DIAGNÓSTICO
        # ─────────────────────────────────────────

        logger.info(
            "MENSAJE RECIBIDO: user_id=%s username=%s texto=%r",
            user.id if user else None,
            user.username if user else None,
            message.text,
        )

        # ─────────────────────────────────────────
        # COMPROBAR ADMIN
        # ─────────────────────────────────────────

        if not user or user.id not in config.admin_ids:
            logger.info(
                "Mensaje ignorado de usuario no autorizado "
                "(user_id=%s)",
                user.id if user else "desconocido",
            )
            return

        logger.info(
            "Usuario autorizado: user_id=%s",
            user.id,
        )

        # ─────────────────────────────────────────
        # SI ESTAMOS ESPERANDO EL NOMBRE
        # ─────────────────────────────────────────

        pending_product = context.user_data.get(
            "pending_product"
        )

        if pending_product:

            name = message.text.strip()

            if not name:
                await message.reply_text(
                    "❌ El nombre no puede estar vacío. "
                    "Escribe el nombre que quieres usar."
                )
                return

            pending_product.name = name

            context.user_data.pop(
                "pending_product",
                None,
            )

            caption = build_find_caption(
                pending_product
            )

            logger.info(
                "Publicando FIND para user_id=%s",
                user.id,
            )

            try:

                if pending_product.images:

                    media = [
                        InputMediaPhoto(url)
                        for url in pending_product.images
                    ]

                    media[0] = InputMediaPhoto(
                        media[0].media,
                        caption=caption,
                        parse_mode="HTML",
                    )

                    await context.bot.send_media_group(
                        chat_id=CHANNEL_ID,
                        media=media,
                    )

                else:

                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=caption,
                        parse_mode="HTML",
                    )

                await message.reply_text(
                    "✅ FIND publicado en el canal."
                )

                logger.info(
                    "FIND publicado correctamente "
                    "para user_id=%s",
                    user.id,
                )

            except Exception:

                logger.exception(
                    "Error al publicar el FIND en el canal "
                    "para user_id=%s",
                    user.id,
                )

                await message.reply_text(
                    "Hubo un error al publicar "
                    "el FIND en el canal."
                )

            return

        # ─────────────────────────────────────────
        # DETECTAR LINK
        # ─────────────────────────────────────────

        link_match = find_product_link(
            message.text
        )

        if link_match is None:
            return

        platform, product_url = link_match

        logger.info(
            "Link de %s detectado: %s",
            platform.value,
            product_url,
        )

        # ─────────────────────────────────────────
        # PROCESAR PRODUCTO
        # ─────────────────────────────────────────
        #
        # IMPORTANTE:
        # No bloqueamos ninguna plataforma aquí.
        #
        # El dispatcher decide qué adaptador utilizar:
        #
        # Weidian  -> weidian.py
        # Taobao   -> taobao.py
        # 1688     -> platform_1688.py
        #

        try:

            product = await process(
                platform,
                product_url,
            )

        except UnsupportedPlatformError as e:

            logger.warning(
                "Plataforma no soportada: %s",
                platform.value,
            )

            await message.reply_text(
                str(e)
            )

            return

        except ProductFetchError as e:

            logger.exception(
                "Fallo al procesar producto de %s: %s",
                platform.value,
                e,
            )

            await message.reply_text(
                f"❌ No pude obtener los datos del producto:\n\n"
                f"{e}"
            )

            return

        except Exception as e:

            logger.exception(
                "Error inesperado procesando producto "
                "de %s: %s",
                platform.value,
                e,
            )

            await message.reply_text(
                "❌ Ocurrió un error inesperado "
                "al procesar el producto."
            )

            return

        # ─────────────────────────────────────────
        # PRECIO
        # ─────────────────────────────────────────

        try:

            product.price = cny_to_eur(
                product.price,
                config.cny_eur_rate,
            )

        except Exception as e:

            logger.exception(
                "Error convirtiendo el precio: %s",
                e,
            )

            await message.reply_text(
                "❌ No pude convertir el precio "
                "del producto."
            )

            return

        # ─────────────────────────────────────────
        # ENLACES
        # ─────────────────────────────────────────

        product.spreadsheet_url = (
            config.spreadsheet_url
        )

        product.sugargoo_url = build_sugargoo_url(
            product_url,
            config.sugargoo_member_id,
        )

        product.usfans_url = build_usfans_product_url(
            product_url,
            config.usfans_ref,
        )

        product.sugargoo_coupon = (
            config.sugargoo_coupon
        )

        product.usfans_coupon = (
            config.usfans_coupon
        )

        logger.info(
            "Enlaces generados para %s | "
            "Sugargoo=%s | USFans=%s",
            platform.value,
            bool(product.sugargoo_url),
            bool(product.usfans_url),
        )

        if not product.sugargoo_url:

            logger.warning(
                "No se pudo generar el enlace "
                "de SugarGoo para %s",
                product_url,
            )

        if not product.usfans_url:

            logger.warning(
                "No se pudo generar el enlace "
                "de USFans para %s",
                product_url,
            )

        # ─────────────────────────────────────────
        # GUARDAR PRODUCTO Y PEDIR NOMBRE
        # ─────────────────────────────────────────

        context.user_data[
            "pending_product"
        ] = product

        logger.info(
            "Producto procesado correctamente: "
            "platform=%s name=%r price=%r images=%d",
            platform.value,
            product.name,
            product.price,
            len(product.images),
        )

        await message.reply_text(
            "🏷️ ¿Qué nombre quieres ponerle al FIND?\n\n"
            "Escribe exactamente el nombre que quieres "
            "que aparezca.\n\n"
            "Ejemplo:\n"
            "Maison Margiela Weight Cotton T-Shirt"
        )

    return handle_message
