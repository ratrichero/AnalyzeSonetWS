"""
Telegram Bot Handlers.
"""

import asyncio
import logging
import re
from typing import Optional

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode

from config import config
from bot.keyboards import (
    main_menu_keyboard, timeframe_keyboard,
    popular_coins_keyboard, back_keyboard,
)
from bot.messages import (
    welcome_message, help_message,
    format_single_report, format_mtf_report,
)
from analyzer import analyze_single, analyze_multi_timeframe
from analyzer.data_fetcher import fetcher

logger = logging.getLogger(__name__)

# ── Trạng thái người dùng (in-memory, đủ dùng) ──────────────────────
user_state: dict = {}   # {user_id: {"mode": "analyze"|"recommend", "step": ...}}


# ══════════════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════════════

def _normalize_symbol(text: str) -> str:
    text = text.strip().upper()
    if not text.endswith("USDT"):
        text += "USDT"
    return text


async def _send_loading(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
    )
    return msg.message_id


async def _edit_or_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    msg_id: Optional[int] = None,
):
    kwargs = dict(
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
    if msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=msg_id,
                **kwargs,
            )
            return
        except Exception:
            pass
    await context.bot.send_message(chat_id=update.effective_chat.id, **kwargs)


# ══════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        welcome_message(),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        help_message(),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard(),
    )


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu phân tích – có thể kèm tên coin /analyze BTC"""
    args = context.args
    uid  = update.effective_user.id

    if args:
        symbol = _normalize_symbol(args[0])
        user_state[uid] = {"mode": "analyze", "symbol": symbol}
        await update.message.reply_text(
            f"📊 Chọn khung giờ phân tích *{symbol}*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=timeframe_keyboard(symbol, "analyze"),
        )
    else:
        user_state[uid] = {"mode": "analyze"}
        await update.message.reply_text(
            "📊 *Phân tích Coin*\n\nNhập tên coin (VD: `BTC`, `ETH`, `SOLUSDT`)\nhoặc chọn từ danh sách:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=popular_coins_keyboard("analyze"),
        )


async def cmd_recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu khuyến nghị – có thể kèm tên coin /recommend ETH"""
    args = context.args
    uid  = update.effective_user.id

    if args:
        symbol = _normalize_symbol(args[0])
        user_state[uid] = {"mode": "recommend", "symbol": symbol}
        await _run_mtf_analysis(update, context, symbol)
    else:
        user_state[uid] = {"mode": "recommend"}
        await update.message.reply_text(
            "🎯 *Khuyến nghị Coin*\n\nNhập tên coin hoặc chọn từ danh sách:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=popular_coins_keyboard("recommend"),
        )


# ══════════════════════════════════════════════════════════════════════
# TEXT HANDLER – Nhận input coin từ người dùng
# ══════════════════════════════════════════════════════════════════════

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()
    state = user_state.get(uid, {})
    mode  = state.get("mode", "analyze")

    symbol = _normalize_symbol(text)

    # Validate
    loading_id = await _send_loading(update, context, f"🔍 Đang kiểm tra {symbol}...")
    try:
        valid = await fetcher.validate_symbol(symbol)
    except Exception:
        valid = True   # Nếu không validate được, thử luôn

    if not valid:
        await _edit_or_send(
            update, context,
            f"❌ Không tìm thấy `{symbol}` trên Binance Futures.\n"
            f"Thử lại với tên khác:",
            back_keyboard(),
            loading_id,
        )
        return

    await context.bot.delete_message(update.effective_chat.id, loading_id)

    user_state[uid] = {"mode": mode, "symbol": symbol}

    if mode == "recommend":
        await _run_mtf_analysis(update, context, symbol)
    else:
        await update.message.reply_text(
            f"📊 Chọn khung giờ phân tích *{symbol}*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=timeframe_keyboard(symbol, "analyze"),
        )


# ══════════════════════════════════════════════════════════════════════
# CALLBACK QUERY HANDLER
# ══════════════════════════════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid  = update.effective_user.id

    # ── Menu điều hướng ─────────────────────────────────────────
    if data == "menu_main":
        await query.edit_message_text(
            welcome_message(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )

    elif data == "menu_analyze":
        user_state[uid] = {"mode": "analyze"}
        await query.edit_message_text(
            "📊 *Phân tích Coin*\n\nNhập tên coin hoặc chọn:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=popular_coins_keyboard("analyze"),
        )

    elif data == "menu_recommend":
        user_state[uid] = {"mode": "recommend"}
        await query.edit_message_text(
            "🎯 *Khuyến nghị Coin*\n\nNhập tên coin hoặc chọn:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=popular_coins_keyboard("recommend"),
        )

    elif data == "menu_popular":
        mode = user_state.get(uid, {}).get("mode", "analyze")
        await query.edit_message_text(
            "⭐ *Coin phổ biến* – Chọn để phân tích:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=popular_coins_keyboard(mode),
        )

    elif data == "menu_help":
        await query.edit_message_text(
            help_message(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard(),
        )

    # ── Chọn coin từ danh sách ──────────────────────────────────
    elif data.startswith("select:"):
        _, mode, symbol = data.split(":", 2)
        user_state[uid] = {"mode": mode, "symbol": symbol}
        if mode == "recommend":
            await query.edit_message_text(
                f"⏳ Đang phân tích *{symbol}*...",
                parse_mode=ParseMode.MARKDOWN,
            )
            await _run_mtf_analysis_callback(query, context, symbol)
        else:
            await query.edit_message_text(
                f"📊 Chọn khung giờ phân tích *{symbol}*:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=timeframe_keyboard(symbol, "analyze"),
            )

    # ── Phân tích theo timeframe ────────────────────────────────
    elif data.startswith("analyze:"):
        _, symbol, tf = data.split(":", 2)
        await query.edit_message_text(
            f"⏳ Đang phân tích *{symbol}* [{tf.upper()}]...",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _run_single_analysis(query, context, symbol, tf)

    # ── Khuyến nghị MTF ────────────────────────────────────────
    elif data.startswith("recommend:"):
        _, symbol, tf = data.split(":", 2)
        await query.edit_message_text(
            f"⏳ Đang phân tích đa khung *{symbol}*...",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _run_mtf_analysis_callback(query, context, symbol)


# ══════════════════════════════════════════════════════════════════════
# CORE ANALYSIS RUNNERS
# ══════════════════════════════════════════════════════════════════════

async def _run_single_analysis(query, context, symbol: str, tf: str):
    try:
        report = await analyze_single(symbol, tf)
        text   = format_single_report(report)
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_back_and_refresh_keyboard(symbol, tf),
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.exception(f"Lỗi phân tích {symbol} {tf}: {e}")
        await query.edit_message_text(
            f"❌ Lỗi khi phân tích {symbol} [{tf}]:\n`{str(e)[:200]}`\n\nThử lại sau.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard(),
        )


async def _run_mtf_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE, symbol: str):
    msg_id = (await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"⏳ Đang phân tích đa khung *{symbol}*...",
        parse_mode=ParseMode.MARKDOWN,
    )).message_id

    try:
        mtf    = await analyze_multi_timeframe(symbol)
        text   = format_mtf_report(mtf)
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=msg_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_mtf_action_keyboard(symbol),
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.exception(f"Lỗi MTF {symbol}: {e}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=msg_id,
            text=f"❌ Lỗi: `{str(e)[:200]}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard(),
        )


async def _run_mtf_analysis_callback(query, context, symbol: str):
    try:
        mtf  = await analyze_multi_timeframe(symbol)
        text = format_mtf_report(mtf)
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_mtf_action_keyboard(symbol),
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.exception(f"Lỗi MTF {symbol}: {e}")
        await query.edit_message_text(
            f"❌ Lỗi: `{str(e)[:200]}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard(),
        )


# ══════════════════════════════════════════════════════════════════════
# INLINE KEYBOARDS PHỤ
# ══════════════════════════════════════════════════════════════════════

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _back_and_refresh_keyboard(symbol: str, tf: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Làm mới",    callback_data=f"analyze:{symbol}:{tf}"),
            InlineKeyboardButton("🎯 Khuyến nghị", callback_data=f"recommend:{symbol}:all"),
        ],
        [
            InlineKeyboardButton("📋 Khung khác",  callback_data=f"select:analyze:{symbol}"),
            InlineKeyboardButton("🔙 Menu",         callback_data="menu_main"),
        ],
    ])


def _mtf_action_keyboard(symbol: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Làm mới",     callback_data=f"recommend:{symbol}:all"),
            InlineKeyboardButton("📊 Phân tích",    callback_data=f"select:analyze:{symbol}"),
        ],
        [InlineKeyboardButton("🔙 Menu chính",     callback_data="menu_main")],
    ])