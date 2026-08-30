"""Handler de mensajes: detecta enlaces, genera el FIND y lo publica."""

import asyncio
import logging

from telegram import InputMediaPhoto, Update
from telegram.error import NetworkError, RetryAfter, TimedOut
from telegram.ext import ContextTypes

from product_processor.base import ProductFetchError
from product_processor.dispatcher import (
    UnsupportedPlatformError,
    process,
)

from utils.affiliate import (
    build_sugargoo_url,
    build_usfans_product_url,
)

from utils.find_formatter import build_find_caption
from utils.link_parser import find_product_link
from utils.pricing import cny_to_eur


logger = logging.getLogger("sugarfinds")


CHANNEL_ID = -1004404116341


# ---------------------------------------------------------------------------
# CONFIGURACIÓN DE TIMEOUTS
# ---------------------------------------------------------------------------

# Tiempo máximo permitido para procesar un producto completo.
PRODUCT_PROCESS_TIMEOUT = 180

# Número máximo de intentos para enviar un FIND.
TELEGRAM_SEND_RETRIES = 3


# ---------------------------------------------------------------------------
# ENVÍO ROBUSTO DE MEDIA GROUP
# ---------------------------------------------------------------------------

async def send_media_group_with_retry(
    bot,
    chat_id,
    media,
):
    """
    Envía un álbum a Telegram con reintentos ante errores de red/timeout.
    """

    last_error = None

    for attempt in range(1, TELEGRAM_SEND_RETRIES + 1):

        try:

            logger.info(
                "Enviando media group a Telegram "
                "(intento %d/%d)",
                attempt,
                TELEGRAM_SEND_RETRIES,
            )

            result = await bot.send_media_group(
                chat_id=chat_id,
                media=media,
            )

            logger.info(
                "Media group enviado correctamente "
                "en intento %d",
                attempt,
            )

            return result

        except RetryAfter as e:

            last_error = e

            wait_seconds = max(
                1,
                int(e.retry_after),
            )

            logger.warning(
                "Telegram pidió esperar %ss "
                "antes de volver a intentar.",
                wait_seconds,
            )

            await asyncio.sleep(
                wait_seconds
            )

        except (TimedOut, NetworkError) as e:

            last_error = e

            if attempt >= TELEGRAM_SEND_RETRIES:
                break

            wait_seconds = 3 * attempt

            logger.warning(
                "Timeout/error de red enviando "
                "media group: %s. "
                "Reintentando en %ss...",
                e,
                wait_seconds,
            )

            await asyncio.sleep(
                wait_seconds
            )

        except Exception:
            raise

    if last_error:
        raise last_error

    raise RuntimeError(
        "No se pudo enviar el media group."
    )


# ---------------------------------------------------------------------------
# ENVÍO ROBUSTO DE MENSAJES
# ---------------------------------------------------------------------------

async def send_message_with_retry(
    bot,
    chat_id,
    text,
    parse_mode=None,
):
    """
    Envía un mensaje de Telegram con reintentos.
    """

    last_error = None

    for attempt in range(1, TELEGRAM_SEND_RETRIES + 1):

        try:

            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
            )

        except RetryAfter as e:

            last_error = e

            wait_seconds = max(
                1,
                int(e.retry_after),
            )

            logger.warning(
                "Telegram pidió esperar %ss "
                "antes de enviar el mensaje.",
                wait_seconds,
            )

            await asyncio.sleep(
                wait_seconds
            )

        except (TimedOut, NetworkError) as e:

            last_error = e

            if attempt >= TELEGRAM_SEND_RETRIES:
                break

            wait_seconds = 2 * attempt

            logger.warning(
                "Timeout/error enviando mensaje "
                "a Telegram: %s. "
                "Reintentando en %ss...",
                e,
                wait_seconds,
            )

            await asyncio.sleep(
                wait_seconds
            )

        except Exception:
            raise

    if last_error:
        raise last_error

    raise RuntimeError(
        "No se pudo enviar el mensaje."
    )


# ---------------------------------------------------------------------------
# HANDLER
# ---------------------------------------------------------------------------

def build_message_handler(config):

    async def handle_message(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):

        message = update.message

        if not message or not message.text:
            return

        user = update.effective_user

        # -------------------------------------------------------------------
        # DIAGNÓSTICO
        # -------------------------------------------------------------------

        logger.info(
            "MENSAJE RECIBIDO: user_id=%s username=%s texto=%r",
            user.id if user else None,
            user.username if user else None,
            message.text,
        )

        # -------------------------------------------------------------------
        # COMPROBAR ADMIN
        # -------------------------------------------------------------------

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

        # -------------------------------------------------------------------
        # SI ESTAMOS ESPERANDO EL NOMBRE
        # -------------------------------------------------------------------

        pending_product = context.user_data.get(
            "pending_product"
        )

        if pending_product:

            name = message.text.strip()

            if not name:

                await send_message_with_retry(
                    context.bot,
                    message.chat_id,
                    (
                        "❌ El nombre no puede estar vacío. "
                        "Escribe el nombre que quieres usar."
                    ),
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

                # -----------------------------------------------------------
                # FOTOS
                # -----------------------------------------------------------

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

                    await send_media_group_with_retry(
                        context.bot,
                        CHANNEL_ID,
                        media,
                    )

                # -----------------------------------------------------------
                # SIN FOTOS
                # -----------------------------------------------------------

                else:

                    await send_message_with_retry(
                        context.bot,
                        CHANNEL_ID,
                        caption,
                        parse_mode="HTML",
                    )

                # -----------------------------------------------------------
                # CONFIRMACIÓN
                # -----------------------------------------------------------

                await send_message_with_retry(
                    context.bot,
                    message.chat_id,
                    "✅ FIND publicado en el canal.",
                )

                logger.info(
                    "FIND publicado correctamente "
                    "para user_id=%s",
                    user.id,
                )

            except Exception:

                logger.exception(
                    "Error al publicar el FIND "
                    "en el canal para user_id=%s",
                    user.id,
                )

                try:

                    await send_message_with_retry(
                        context.bot,
                        message.chat_id,
                        (
                            "❌ Hubo un error al publicar "
                            "el FIND en el canal."
                        ),
                    )

                except Exception:

                    logger.exception(
                        "No se pudo enviar siquiera "
                        "el mensaje de error al usuario."
                    )

            return

        # -------------------------------------------------------------------
        # DETECTAR LINK
        # -------------------------------------------------------------------

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

        # -------------------------------------------------------------------
        # PROCESAR PRODUCTO
        # -------------------------------------------------------------------

        try:

            logger.info(
                "Comenzando procesamiento de producto "
                "platform=%s",
                platform.value,
            )

            # IMPORTANTE:
            # Si un scraper se queda colgado, nunca podrá ocupar el
            # procesamiento indefinidamente.
            product = await asyncio.wait_for(
                process(
                    platform,
                    product_url,
                ),
                timeout=PRODUCT_PROCESS_TIMEOUT,
            )

            logger.info(
                "Procesamiento terminado correctamente "
                "platform=%s",
                platform.value,
            )

        except asyncio.TimeoutError:

            logger.error(
                "TIMEOUT procesando producto de %s "
                "después de %ss: %s",
                platform.value,
                PRODUCT_PROCESS_TIMEOUT,
                product_url,
            )

            await send_message_with_retry(
                context.bot,
                message.chat_id,
                (
                    "⏱️ El producto ha tardado demasiado "
                    "en procesarse.\n\n"
                    "Prueba de nuevo con el enlace."
                ),
            )

            return

        except UnsupportedPlatformError as e:

            logger.warning(
                "Plataforma no soportada: %s",
                platform.value,
            )

            await send_message_with_retry(
                context.bot,
                message.chat_id,
                str(e),
            )

            return

        except ProductFetchError as e:

            logger.exception(
                "Fallo al procesar producto de %s: %s",
                platform.value,
                e,
            )

            await send_message_with_retry(
                context.bot,
                message.chat_id,
                (
                    "❌ No pude obtener los datos "
                    "del producto:\n\n"
                    f"{e}"
                ),
            )

            return

        except Exception as e:

            logger.exception(
                "Error inesperado procesando producto "
                "de %s: %s",
                platform.value,
                e,
            )

            try:

                await send_message_with_retry(
                    context.bot,
                    message.chat_id,
                    (
                        "❌ Ocurrió un error inesperado "
                        "al procesar el producto."
                    ),
                )

            except Exception:

                logger.exception(
                    "No se pudo informar al usuario "
                    "del error de procesamiento."
                )

            return

        # -------------------------------------------------------------------
        # PRECIO
        # -------------------------------------------------------------------

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

            await send_message_with_retry(
                context.bot,
                message.chat_id,
                (
                    "❌ No pude convertir el precio "
                    "del producto."
                ),
            )

            return

        # -------------------------------------------------------------------
        # ENLACES
        # -------------------------------------------------------------------

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

        # -------------------------------------------------------------------
        # GUARDAR PRODUCTO Y PEDIR NOMBRE
        # -------------------------------------------------------------------

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

        await send_message_with_retry(
            context.bot,
            message.chat_id,
            (
                "🏷️ ¿Qué nombre quieres ponerle al FIND?\n\n"
                "Escribe exactamente el nombre que quieres "
                "que aparezca.\n\n"
                "Ejemplo:\n"
                "Maison Margiela Weight Cotton T-Shirt"
            ),
        )

    return handle_message
