"""
Entry point.
BOT_MODE=polling  → dev local, không cần domain
BOT_MODE=webhook  → production trên Render
"""

import asyncio
import logging
import sys

from config import config

logging.basicConfig(
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def run_polling():
    """Local dev – không cần domain, không cần Render."""
    from telegram.ext import (
        Application, CommandHandler,
        MessageHandler, CallbackQueryHandler, filters,
    )
    from bot.handlers import (
        cmd_start, cmd_help, cmd_analyze, cmd_recommend,
        handle_text, handle_callback,
    )
    from cache.cache_manager import create_cache_manager

    logger.info("🔄 Mode: POLLING (local dev)")
    cache = create_cache_manager(config)

    app = (
        Application.builder()
        .token(config.TELEGRAM_TOKEN)
        .concurrent_updates(True)
        .build()
    )
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("analyze",   cmd_analyze))
    app.add_handler(CommandHandler("recommend", cmd_recommend))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_text
    ))

    async def post_init(application):
        async def _cleanup():
            while True:
                await asyncio.sleep(300)
                try:
                    n = await cache.clear_expired()
                    if n > 0:
                        logger.info(f"Cache: xóa {n} entries hết hạn")
                except Exception as e:
                    logger.error(f"Cache cleanup: {e}")
        asyncio.create_task(_cleanup())
        logger.info("✅ Bot polling sẵn sàng!")

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)


def run_webhook():
    """Production – chạy FastAPI + uvicorn trên Render."""
    import uvicorn
    from webhook import web_app

    if not config.WEBHOOK_URL:
        logger.error("❌ WEBHOOK_URL chưa cấu hình trong .env")
        sys.exit(1)

    logger.info("🌐 Mode: WEBHOOK (production)")
    logger.info(f"   WEBHOOK_URL : {config.WEBHOOK_URL}")
    logger.info(f"   Listen      : {config.HOST}:{config.PORT}")

    uvicorn.run(
        web_app,
        host=config.HOST,
        port=config.PORT,
        log_level="warning",
        access_log=False,
    )


def main():
    if not config.TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN chưa cấu hình!")
        sys.exit(1)

    logger.info(f"🤖 Crypto Futures Analyzer")
    logger.info(f"   Mode  : {config.BOT_MODE.upper()}")
    logger.info(f"   Cache : {config.CACHE_BACKEND}")

    if config.BOT_MODE == "webhook":
        run_webhook()
    else:
        run_polling()


if __name__ == "__main__":
    main()