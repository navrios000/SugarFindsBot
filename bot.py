"""Punto de entrada del bot."""

import asyncio
import logging
import os
import sys

from aiohttp import web
from telegram.ext import Application, MessageHandler, filters

from config import ConfigError, load_config
from handlers.message_handler import build_message_handler
from utils.logger import setup_logger

# Carga .env en desarrollo local.
load_dotenv = None

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

logging.getLogger("telegram").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.INFO)

logger = setup_logger()


# ---------------------------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------------------------

async def health_check(request):
    return web.Response(text="Sugar Finds Bot OK")


# ---------------------------------------------------------------------------
# BOT
# ---------------------------------------------------------------------------

async def run_bot():

    try:
        config = load_config()

    except ConfigError as e:
        logger.error("Error de configuración: %s", e)
        return 1

    logger.info(
        "ADMIN_IDS cargados: %d administrador(es)",
        len(config.admin_ids),
    )

    # IMPORTANTE:
    # concurrent_updates(True) permite que un producto que esté tardando
    # no bloquee la recepción de otros mensajes.
    app = (
        Application.builder()
        .token(config.bot_token)
        .concurrent_updates(True)
        .build()
    )

    handler = build_message_handler(config)

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handler,
        )
    )

    # -----------------------------------------------------------------------
    # SERVIDOR WEB PARA RENDER
    # -----------------------------------------------------------------------

    port = int(os.environ.get("PORT", 10000))

    web_app = web.Application()

    web_app.router.add_get(
        "/",
        health_check,
    )

    runner = web.AppRunner(web_app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port,
    )

    await site.start()

    logger.info(
        "Servidor web escuchando en el puerto %s",
        port,
    )

    logger.info(
        "Sugar Finds Bot iniciado "
        "(Fase 2 - FINDs automáticos)..."
    )

    # -----------------------------------------------------------------------
    # ERRORES DE POLLING
    # -----------------------------------------------------------------------

    def on_polling_error(error):

        logger.error(
            "Error de polling detectado: %s",
            error,
            exc_info=True,
        )

    # -----------------------------------------------------------------------
    # TELEGRAM
    # -----------------------------------------------------------------------

    try:

        await app.initialize()

        me = await app.bot.get_me()

        logger.info(
            "Autenticado en Telegram como @%s (id=%s)",
            me.username,
            me.id,
        )

        deleted = await app.bot.delete_webhook(
            drop_pending_updates=True,
        )

        logger.info(
            "delete_webhook() ejecutado (resultado=%s)",
            deleted,
        )

        await app.start()

        await app.updater.start_polling(
            drop_pending_updates=True,
            error_callback=on_polling_error,
        )

        logger.info(
            "Polling iniciado correctamente. "
            "Bot listo para recibir mensajes."
        )

        # Mantener vivo el proceso.
        await asyncio.Event().wait()

    except asyncio.CancelledError:

        logger.info(
            "Bot cancelado. Cerrando correctamente..."
        )

        raise

    except Exception:

        logger.exception(
            "Fallo inesperado al ejecutar el bot"
        )

        return 1

    finally:

        logger.info(
            "Iniciando apagado limpio del bot..."
        )

        try:

            if app.updater and app.updater.running:
                await app.updater.stop()

        except Exception:

            logger.exception(
                "Error deteniendo el updater"
            )

        try:

            if app.running:
                await app.stop()

        except Exception:

            logger.exception(
                "Error deteniendo Application"
            )

        try:

            await app.shutdown()

        except Exception:

            logger.exception(
                "Error haciendo shutdown de Application"
            )

        try:

            await runner.cleanup()

        except Exception:

            logger.exception(
                "Error cerrando servidor web"
            )

        logger.info(
            "Bot cerrado."
        )

    return 0


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    sys.exit(
        asyncio.run(
            run_bot()
        )
    )


if __name__ == "__main__":
    main()
