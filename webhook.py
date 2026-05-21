"""
FastAPI webhook server cho Render.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from config import config

import os
import sys

# Fix path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

logger = logging.getLogger(__name__)

_ptb_app: Application = None


def _build_ptb_app() -> Application:
    from bot.handlers import (
        cmd_start, cmd_help, cmd_analyze, cmd_recommend,
        handle_text, handle_callback,
    )
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("analyze",   cmd_analyze))
    app.add_handler(CommandHandler("recommend", cmd_recommend))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_text
    ))
    return app


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ptb_app

    logger.info("🚀 Khởi động PTB...")
    _ptb_app = _build_ptb_app()
    await _ptb_app.initialize()
    await _ptb_app.start()

    # Đăng ký webhook
    webhook_full_url = (
        f"{config.WEBHOOK_URL.rstrip('/')}"
        f"/webhook/{config.WEBHOOK_SECRET}"
    )
    try:
        await _ptb_app.bot.set_webhook(
            url=webhook_full_url,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        info = await _ptb_app.bot.get_webhook_info()
        logger.info(f"✅ Webhook: {info.url}")
    except Exception as e:
        logger.error(f"❌ Set webhook thất bại: {e}")

    # Cache cleanup
    from cache.cache_manager import create_cache_manager
    cache = create_cache_manager(config)

    async def _cleanup():
        while True:
            await asyncio.sleep(300)
            try:
                n = await cache.clear_expired()
                if n > 0:
                    logger.info(f"Cache: xóa {n} entries")
            except Exception as e:
                logger.error(f"Cache cleanup: {e}")

    asyncio.create_task(_cleanup())

    yield

    # Shutdown
    logger.info("🛑 Shutdown...")
    try:
        await _ptb_app.bot.delete_webhook()
        await _ptb_app.stop()
        await _ptb_app.shutdown()
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


web_app = FastAPI(
    title="Crypto Futures Analyzer",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


@web_app.get("/")
async def root():
    return {"status": "ok", "service": "Crypto Futures Analyzer"}


@web_app.get("/health")
async def health():
    bot_ok   = False
    username = None
    if _ptb_app:
        try:
            me       = await _ptb_app.bot.get_me()
            bot_ok   = True
            username = me.username
        except Exception as e:
            logger.error(f"Health check: {e}")

    return JSONResponse(
        status_code=200,
        content={
            "status":   "ok" if bot_ok else "degraded",
            "bot_ok":   bot_ok,
            "username": username,
            "mode":     "webhook",
        },
    )


@web_app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != config.WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    update = Update.de_json(data, _ptb_app.bot)
    asyncio.create_task(_ptb_app.process_update(update))

    return JSONResponse(content={"ok": True})