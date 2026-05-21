"""
Entry point.
BOT_MODE=polling  → dev local
BOT_MODE=webhook  → production trên Render
"""

import asyncio
import logging
import os
import sys

# ── Fix Python path – đảm bảo import hoạt động mọi nơi ───────
# Thêm thư mục chứa main.py vào sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ── Đọc PORT/HOST sớm từ os.environ ──────────────────────────
_PORT = int(os.environ.get("PORT", "10000"))
_HOST = os.environ.get("HOST", "0.0.0.0")
_MODE = os.environ.get("BOT_MODE", "polling")

from config import config

# ── Logging – KHÔNG dùng FileHandler trên Render ─────────────
logging.basicConfig(
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def run_polling():
    from telegram.ext import (
        Application, CommandHandler,
        MessageHandler, CallbackQueryHandler, filters,
    )
    from bot.handlers import (
        cmd_start, cmd_help, cmd_analyze, cmd_recommend,
        handle_text, handle_callback,
    )
    from cache.cache_manager import create_cache_manager

    logger.info("🔄 Mode: POLLING")
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
                        logger.info(f"Cache cleanup: {n} entries")
                except Exception as e:
                    logger.error(f"Cache cleanup: {e}")
        asyncio.create_task(_cleanup())
        logger.info("✅ Bot polling sẵn sàng!")

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)


def run_webhook():
    import uvicorn

    if not config.WEBHOOK_URL:
        logger.error("❌ WEBHOOK_URL chưa cấu hình!")
        sys.exit(1)

    logger.info("🌐 Mode: WEBHOOK")
    logger.info(f"   Host : {_HOST}:{_PORT}")
    logger.info(f"   URL  : {config.WEBHOOK_URL}")

    uvicorn.run(
        "webhook:web_app",
        host=_HOST,
        port=_PORT,
        log_level="info",
        access_log=True,
    )


def main():
    if not config.TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN chưa cấu hình!")
        sys.exit(1)

    logger.info(f"🤖 Crypto Futures Analyzer")
    logger.info(f"   Mode : {_MODE.upper()}")
    logger.info(f"   Port : {_PORT}")
    logger.info(f"   Host : {_HOST}")

    if _MODE == "webhook":
        run_webhook()
    else:
        run_polling()


if __name__ == "__main__":
    main()