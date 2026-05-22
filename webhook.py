"""
FastAPI webhook server cho Render.
Telegram gọi vào đây khi user tương tác bot.
"""

# ── Fix Python path trước mọi import khác ─────────────────────
import os
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ─────────────────────────────────────────────────────────────
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse, Response
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import config

logger = logging.getLogger(__name__)

_ptb_app: Application | None = None
_cleanup_task: asyncio.Task | None = None


def _build_ptb_app() -> Application:
    """
    Tạo Telegram Application.
    Import handlers bên trong function để tránh circular import.
    """
    from bot.handlers import (
        cmd_start,
        cmd_help,
        cmd_analyze,
        cmd_recommend,
        handle_text,
        handle_callback,
    )

    app = (
        Application.builder()
        .token(config.TELEGRAM_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("recommend", cmd_recommend))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


async def _process_update_safe(update: Update):
    """
    Xử lý Telegram update dạng background task.
    Bọc try/except để lỗi trong bot không làm task bị unobserved exception.
    """
    global _ptb_app

    if _ptb_app is None:
        logger.error("PTB app chưa sẵn sàng, bỏ qua update")
        return

    try:
        await _ptb_app.process_update(update)
    except Exception as e:
        logger.exception(f"Lỗi khi process Telegram update: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup/shutdown lifecycle cho FastAPI.
    """
    global _ptb_app, _cleanup_task

    logger.info("🚀 Khởi động PTB...")

    # ── STARTUP ───────────────────────────────────────────────
    _ptb_app = _build_ptb_app()

    await _ptb_app.initialize()
    await _ptb_app.start()

    webhook_full_url = (
        f"{config.WEBHOOK_URL.rstrip('/')}"
        f"/webhook/{config.WEBHOOK_SECRET}"
    )

    try:
        await _ptb_app.bot.set_webhook(
            url=webhook_full_url,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
            max_connections=40,
        )
        info = await _ptb_app.bot.get_webhook_info()
        logger.info(f"✅ Webhook đã đăng ký: {info.url}")
        logger.info(f"Pending updates: {info.pending_update_count}")
    except Exception as e:
        logger.exception(f"❌ Set webhook thất bại: {e}")

    # ── Background cache cleanup ──────────────────────────────
    from cache.cache_manager import create_cache_manager

    cache = create_cache_manager(config)

    async def _cleanup():
        while True:
            await asyncio.sleep(300)
            try:
                n = await cache.clear_expired()
                if n > 0:
                    logger.info(f"Cache cleanup: xóa {n} entries")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")

    _cleanup_task = asyncio.create_task(_cleanup())

    logger.info("✅ Server sẵn sàng!")

    yield

    # ── SHUTDOWN ──────────────────────────────────────────────
    logger.info("🛑 Shutdown...")

    # 1. Hủy background cleanup task
    if _cleanup_task:
        _cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await _cleanup_task

    # 2. Đóng Binance aiohttp session để tránh Unclosed client session
    try:
        from analyzer.data_fetcher import fetcher
        await fetcher.close()
        logger.info("✅ Đã đóng Binance aiohttp session")
    except Exception as e:
        logger.error(f"Lỗi khi đóng fetcher session: {e}")

    # 3. KHÔNG delete webhook trên Render production
    # Nếu delete webhook khi Render sleep/restart, Telegram có thể không gọi lại service.
    delete_on_shutdown = os.getenv("DELETE_WEBHOOK_ON_SHUTDOWN", "false").lower() == "true"

    try:
        if _ptb_app:
            if delete_on_shutdown:
                await _ptb_app.bot.delete_webhook()
                logger.info("Webhook đã được xóa theo cấu hình DELETE_WEBHOOK_ON_SHUTDOWN=true")
            else:
                logger.info("Giữ nguyên Telegram webhook khi shutdown")

            await _ptb_app.stop()
            await _ptb_app.shutdown()
    except Exception as e:
        logger.error(f"Shutdown PTB error: {e}")

    logger.info("✅ Shutdown hoàn tất")


web_app = FastAPI(
    title="Crypto Futures Analyzer",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


# ══════════════════════════════════════════════════════════════
# HEALTH / ROOT
# ══════════════════════════════════════════════════════════════

@web_app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Crypto Futures Analyzer",
        "mode": "webhook",
    }


@web_app.head("/")
async def root_head():
    """
    Render/port scanner đôi khi gọi HEAD /.
    Nếu không có endpoint này sẽ trả 405 và có thể bị xem là unhealthy.
    """
    return Response(status_code=200)


@web_app.get("/health")
async def health():
    bot_ok = False
    username = None

    if _ptb_app:
        try:
            me = await _ptb_app.bot.get_me()
            bot_ok = True
            username = me.username
        except Exception as e:
            logger.error(f"Health check bot error: {e}")

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok" if bot_ok else "degraded",
            "bot_ok": bot_ok,
            "username": username,
            "mode": "webhook",
        },
    )


@web_app.head("/health")
async def health_head():
    """
    Cho HEAD /health trả 200.
    """
    return Response(status_code=200)


@web_app.get("/webhook/info")
async def webhook_info():
    if not _ptb_app:
        raise HTTPException(status_code=503, detail="Bot chưa sẵn sàng")

    info = await _ptb_app.bot.get_webhook_info()
    return JSONResponse(
        content={
            "url": info.url,
            "pending_update_count": info.pending_update_count,
            "last_error_message": info.last_error_message,
            "last_error_date": str(info.last_error_date) if info.last_error_date else None,
        }
    )


# ══════════════════════════════════════════════════════════════
# TELEGRAM WEBHOOK
# ══════════════════════════════════════════════════════════════

@web_app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    """
    Telegram gọi endpoint này khi user gửi message hoặc bấm nút.
    """
    global _ptb_app

    if secret != config.WEBHOOK_SECRET:
        logger.warning("Webhook request sai secret")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    if _ptb_app is None:
        raise HTTPException(status_code=503, detail="Bot not ready")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    update = Update.de_json(data, _ptb_app.bot)

    # Trả 200 cho Telegram ngay, xử lý update nền
    asyncio.create_task(_process_update_safe(update))

    return JSONResponse(content={"ok": True})