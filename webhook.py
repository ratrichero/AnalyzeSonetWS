"""
FastAPI webhook server.
Telegram chủ động gọi vào đây khi có user tương tác.
Không có request = không tốn tài nguyên tính toán.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from config import config

logger = logging.getLogger(__name__)

# PTB app singleton – dùng chung toàn bộ request
_ptb_app: Application = None


def _build_ptb_app() -> Application:
    """Khởi tạo Telegram bot với đầy đủ handlers."""
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
    """Chạy khi server START và STOP."""
    global _ptb_app

    # ── STARTUP ───────────────────────────────────────────────
    logger.info("🚀 Khởi động webhook server...")

    _ptb_app = _build_ptb_app()
    await _ptb_app.initialize()
    await _ptb_app.start()

    # Đăng ký webhook URL với Telegram
    webhook_url = (
        f"{config.WEBHOOK_URL.rstrip('/')}"
        f"/webhook/{config.WEBHOOK_SECRET}"
    )
    await _ptb_app.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

    info = await _ptb_app.bot.get_webhook_info()
    logger.info(f"✅ Webhook đã đăng ký: {info.url}")

    # Background task dọn cache
    from cache.cache_manager import create_cache_manager
    cache = create_cache_manager(config)

    async def _cache_cleanup():
        while True:
            await asyncio.sleep(300)
            try:
                n = await cache.clear_expired()
                if n > 0:
                    logger.info(f"Cache cleanup: {n} entries")
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")

    asyncio.create_task(_cache_cleanup())
    logger.info(f"✅ Server sẵn sàng – {config.HOST}:{config.PORT}")

    yield  # ← Server đang chạy, xử lý requests

    # ── SHUTDOWN ──────────────────────────────────────────────
    logger.info("🛑 Đang tắt server...")
    await _ptb_app.bot.delete_webhook()
    await _ptb_app.stop()
    await _ptb_app.shutdown()
    logger.info("✅ Shutdown hoàn tất")


# ── Tạo FastAPI app ───────────────────────────────────────────
web_app = FastAPI(
    title="Crypto Futures Analyzer",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


# ── Endpoints ─────────────────────────────────────────────────

@web_app.get("/")
async def root():
    """Render health check mặc định."""
    return {"status": "ok", "service": "Crypto Futures Analyzer Bot"}


@web_app.get("/health")
async def health():
    """
    Health check chi tiết.
    Cron-job.org gọi vào đây mỗi 10 phút để giữ bot không sleep.
    """
    bot_ok   = False
    username = None

    if _ptb_app:
        try:
            me       = await _ptb_app.bot.get_me()
            bot_ok   = True
            username = me.username
        except Exception as e:
            logger.error(f"Health check error: {e}")

    return JSONResponse(
        # Luôn trả 200 để Render không tưởng service chết
        status_code=200,
        content={
            "status":   "ok" if bot_ok else "degraded",
            "bot":      {"ok": bot_ok, "username": username},
            "mode":     "webhook",
        },
    )


@web_app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    """
    Telegram gọi vào đây mỗi khi user gửi message/nhấn nút.
    Chỉ xử lý nếu secret token khớp → tránh request giả mạo.
    """
    # Xác thực secret token
    if secret != config.WEBHOOK_SECRET:
        logger.warning(f"Webhook: sai secret token")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    # Parse JSON từ Telegram
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON",
        )

    # Xử lý update – bất đồng bộ
    # Trả 200 về Telegram ngay, tính toán nặng chạy nền
    update = Update.de_json(data, _ptb_app.bot)
    asyncio.create_task(_ptb_app.process_update(update))

    return JSONResponse(content={"ok": True})