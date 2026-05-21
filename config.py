import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── Telegram ──────────────────────────────────────────────
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")

    # ── Mode: polling (local) | webhook (production) ──────────
    BOT_MODE: str = os.getenv("BOT_MODE", "polling")

    # ── Webhook ───────────────────────────────────────────────
    # Render tự cấp URL dạng: https://ten-service.onrender.com
    WEBHOOK_URL: str   = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "changeme")

    # ── Server ────────────────────────────────────────────────
    # Render yêu cầu lắng nghe 0.0.0.0 và đọc PORT từ env
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "10000"))

    # ── Binance API ───────────────────────────────────────────
    USE_API_KEY: bool    = os.getenv("USE_API_KEY", "false").lower() == "true"
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
    BINANCE_FUTURES_BASE_URL: str = "https://fapi.binance.com"

    # ── Cache ─────────────────────────────────────────────────
    CACHE_BACKEND: str = os.getenv("CACHE_BACKEND", "memory")
    REDIS_URL: str     = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CACHE_TTL: dict = {
        "15m": 5 * 60,
        "1h":  15 * 60,
        "4h":  30 * 60,
        "1d":  60 * 60,
    }

    # ── Phân tích ─────────────────────────────────────────────
    TIMEFRAMES: list = ["15m", "1h", "4h", "1d"]
    KLINE_LIMIT: int = 200
    DEFAULT_COINS: list = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
        "MATICUSDT", "NEARUSDT", "ATOMUSDT", "LTCUSDT", "UNIUSDT",
    ]
    TIMEFRAME_WEIGHTS: dict = {
        "15m": 0.10,
        "1h":  0.20,
        "4h":  0.35,
        "1d":  0.35,
    }

    # ── Risk Management ───────────────────────────────────────
    DEFAULT_RISK_REWARD: float = 2.0   # TP2 = SL * 2
    ATR_SL_MULTIPLIER: float  = 1.5
    ATR_TP1_MULTIPLIER: float = 1.5
    ATR_TP2_MULTIPLIER: float = 3.0
    RR_MIN: float    = 2.0
    RR_TARGET: float = 2.5
    RR_CAP: float    = 8.0

    # ── Rate Limit ────────────────────────────────────────────
    MAX_CONCURRENT_REQUESTS: int = 5
    REQUEST_DELAY_SECONDS: float = 0.2

config = Config()