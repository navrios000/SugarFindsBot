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
from utils.link_parser import Platform, find_product_link
from utils.name_cleaner import clean_product_name
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

        if not user or user.id not in config.admin_ids:
            logger.info(
                "Mensaje ignorado de usuario no autorizado "
                "(user_id=%s)",
                user.id if user else "desconocido",
            )
            return

        link_match = find_product_link(message.text)

        if link_match is None:
            return

        platform, product_url = link_match

        logger.info(
            "Link de %s detectado: %s",
            platform.value,
            product_url,
        )

        if platform != Platform.WEIDIAN:
            await message.reply_text(
                f"Detecté un link de "
                f"{platform.value.capitalize()}, pero esa "
                "plataforma todavía no se procesa "
                "automáticamente."
            )
            return

        try:
            product = await process(
                platform,
                product_url,
            )

        except UnsupportedPlatformError as e:
            await message.reply_text(str(e))
            return

        except ProductFetchError as e:
            logger.exception(
                "Fallo al procesar %s",
                product_url,
            )

            await message.reply_text(
                f"No pude obtener los datos del producto: {e}"
            )
            return

        # ─────────────────────────────────────────
        # LIMPIEZA DEL PRODUCTO
        # ─────────────────────────────────────────

        product.name = clean_product_name(
            product.name
        )

        product.price = cny_to_eur(
            product.price,
            config.cny_eur_rate,
        )

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

        if not product.usfans_url:
            logger.warning(
                "No se pudo generar el enlace de "
                "producto de USFans para %s",
                product_url,
            )

        # ─────────────────────────────────────────
        # CAPTION
        # ─────────────────────────────────────────

        caption = build_find_caption(product)

        # ─────────────────────────────────────────
        # PUBLICACIÓN
        # ─────────────────────────────────────────

        try:

            if product.images:

                media = [
                    InputMediaPhoto(url)
                    for url in product.images
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
                "FIND publicado correctamente para %s",
                product_url,
            )

        except Exception:

            logger.exception(
                "Error al publicar el FIND en el canal"
            )

            await message.reply_text(
                "Hubo un error al publicar "
                "el FIND en el canal."
            )

    return handle_message
