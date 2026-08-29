"""Handler de mensajes de texto: detecta enlaces de producto, genera
el FIND y lo publica en el canal.

Reemplaza al handler de prueba anterior (que solo verificaba que el
bot podía publicar en el canal). La whitelist de administradores se
mantiene igual que en Fase 1.
"""

import logging

from telegram import InputMediaPhoto, Update
from telegram.ext import ContextTypes

from product_processor.base import ProductFetchError
from product_processor.dispatcher import UnsupportedPlatformError, process
from utils.affiliate import build_sugargoo_url
from utils.find_formatter import build_find_caption
from utils.link_parser import Platform, find_product_link

logger = logging.getLogger("sugarfinds")

CHANNEL_ID = -1004404116341


def build_message_handler(config):
    """Crea el handler con la whitelist de administradores y la
    configuración necesaria (spreadsheet, cupones, memberId de SugarGoo)."""

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        if not message or not message.text:
            return

        user = update.effective_user
        if not user or user.id not in config.admin_ids:
            logger.info(
                "Mensaje ignorado de usuario no autorizado (user_id=%s)",
                user.id if user else "desconocido",
            )
            return

        link_match = find_product_link(message.text)
        if link_match is None:
            # No es un link de Weidian/Taobao/1688: no hacemos nada.
            # (Si más adelante quieres que el bot responda algo en este
            # caso, aquí es donde hay que añadirlo.)
            return

        platform, product_url = link_match
        logger.info("Link de %s detectado: %s", platform.value, product_url)

        if platform != Platform.WEIDIAN:
            # Decisión actual: Taobao/1688 se publican manualmente por ahora.
            await message.reply_text(
                f"Detecté un link de {platform.value.capitalize()}, pero esa "
                "plataforma todavía no se procesa automáticamente. "
                "Publica este FIND manualmente por ahora."
            )
            return

        try:
            product = await process(platform, product_url)
        except UnsupportedPlatformError as e:
            await message.reply_text(str(e))
            return
        except ProductFetchError as e:
            logger.exception("Fallo al procesar %s", product_url)
            await message.reply_text(f"No pude obtener los datos del producto: {e}")
            return

        # Campos de plantilla/config: se añaden aquí, nunca en el scraper.
        product.spreadsheet_url = config.spreadsheet_url
        product.sugargoo_url = build_sugargoo_url(product_url, config.sugargoo_member_id)
        product.sugargoo_coupon = config.sugargoo_coupon
        product.usfans_coupon = config.usfans_coupon

        caption = build_find_caption(product)

        try:
            if product.images:
                media = [InputMediaPhoto(url) for url in product.images]
                media[0] = InputMediaPhoto(
                    media[0].media, caption=caption, parse_mode="HTML"
                )
                await context.bot.send_media_group(chat_id=CHANNEL_ID, media=media)
            else:
                # Sin fotos, publicamos solo el texto para no perder el FIND.
                await context.bot.send_message(
                    chat_id=CHANNEL_ID, text=caption, parse_mode="HTML"
                )

            await message.reply_text("✅ FIND publicado en el canal.")
            logger.info("FIND publicado correctamente para %s", product_url)

        except Exception:
            logger.exception("Error al publicar el FIND en el canal")
            await message.reply_text("Hubo un error al publicar el FIND en el canal.")

    return handle_message
