"""Punto de entrada del bot."""

import asyncio
import logging
import os
import sys

from aiohttp import web
from dotenv import load_dotenv
from telegram.ext import Application, MessageHandler, filters

from config import ConfigError, load_config
from handlers.message_handler import build_message_handler
from utils.logger import setup_logger

# Carga las variables de .env si el archivo existe (desarrollo local).
# En Render no hay .env: load_dotenv() simplemente no encuentra nada y
# no hace nada, así que las variables de entorno reales de Render (las
# que se configuran en Settings -> Environment) siguen funcionando igual.
# Por defecto no sobreescribe variables que ya estén puestas en el entorno.
load_dotenv()

# --- DIAGNÓSTICO ---
# Nos aseguramos de que los logs internos de python-telegram-bot / httpx
# (por ejemplo errores de getUpdates, Conflict 409, timeouts, etc.)
# también se vean en los logs de Render, aunque utils/logger.py solo
# configure el logger "sugarfinds". Esto no toca ni sustituye la
# configuración existente: si el root logger ya tenía handlers, esta
# llamada es un no-op (comportamiento estándar de logging.basicConfig).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logging.getLogger("telegram").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.INFO)

logger = setup_logger()


async def health_check(request):
    return web.Response(text="Sugar Finds Bot OK")


async def run_bot():
    try:
        config = load_config()
    except ConfigError as e:
        logger.error("Error de configuración: %s", e)
        return 1

    logger.info("ADMIN_IDS cargados: %d administrador(es)", len(config.admin_ids))

    app = Application.builder().token(config.bot_token).build()

    handler = build_message_handler(config)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))

    port = int(os.environ.get("PORT", 10000))

    web_app = web.Application()
    web_app.router.add_get("/", health_check)

    runner = web.AppRunner(web_app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info("Servidor web escuchando en el puerto %s", port)
    logger.info("Sugar Finds Bot iniciado (Fase 2 - FINDs automáticos de Weidian)...")

    def on_polling_error(error):
        logger.error("Error de polling detectado: %s", error)

    try:
        await app.initialize()

        me = await app.bot.get_me()
        logger.info("Autenticado en Telegram como @%s (id=%s)", me.username, me.id)

        deleted = await app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("delete_webhook() ejecutado (resultado=%s)", deleted)

        await app.start()
        await app.updater.start_polling(
            drop_pending_updates=True,
            error_callback=on_polling_error,
        )

        logger.info(
            "start_polling() devuelto correctamente: el bot debería estar "
            "recibiendo actualizaciones ahora"
        )

        await asyncio.Event().wait()

    except Exception:
        logger.exception("Fallo inesperado al ejecutar el bot")
        return 1

    finally:
        if app.updater and app.updater.running:
            await app.updater.stop()

        if app.running:
            await app.stop()

        await app.shutdown()
        await runner.cleanup()

    return 0


def main():
    sys.exit(asyncio.run(run_bot()))


if __name__ == "__main__":
    main()
