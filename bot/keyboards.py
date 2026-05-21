from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import config


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Phân tích Coin",     callback_data="menu_analyze"),
            InlineKeyboardButton("🎯 Khuyến nghị",        callback_data="menu_recommend"),
        ],
        [
            InlineKeyboardButton("⭐ Coin phổ biến",      callback_data="menu_popular"),
            InlineKeyboardButton("ℹ️ Hướng dẫn",         callback_data="menu_help"),
        ],
    ])


def timeframe_keyboard(symbol: str, mode: str = "analyze") -> InlineKeyboardMarkup:
    """mode: analyze | recommend"""
    tfs = config.TIMEFRAMES
    rows = []
    row  = []
    for tf in tfs:
        row.append(InlineKeyboardButton(
            tf.upper(),
            callback_data=f"{mode}:{symbol}:{tf}",
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if mode == "analyze":
        rows.append([InlineKeyboardButton(
            "📈 Tất cả khung (MTF)", callback_data=f"recommend:{symbol}:all"
        )])
    rows.append([InlineKeyboardButton("🔙 Quay lại", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def popular_coins_keyboard(mode: str = "analyze") -> InlineKeyboardMarkup:
    coins = config.DEFAULT_COINS
    rows  = []
    row   = []
    for coin in coins:
        row.append(InlineKeyboardButton(
            coin.replace("USDT", ""),
            callback_data=f"select:{mode}:{coin}",
        ))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Quay lại", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Menu chính", callback_data="menu_main")
    ]])