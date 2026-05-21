import asyncio
import aiohttp
import pandas as pd
import logging
from typing import Optional
from config import config
from cache.cache_manager import create_cache_manager

logger = logging.getLogger(__name__)

# Semaphore toàn cục – tránh flood Binance
_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_REQUESTS)

# Cache singleton
_cache = create_cache_manager(config)


class DataFetcher:
    BASE_URL = config.BINANCE_FUTURES_BASE_URL

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------
    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            headers = {}
            if config.USE_API_KEY and config.BINANCE_API_KEY:
                headers["X-MBX-APIKEY"] = config.BINANCE_API_KEY
            self.session = aiohttp.ClientSession(headers=headers)

    # ------------------------------------------------------------------
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # ------------------------------------------------------------------
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = config.KLINE_LIMIT,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        Lấy dữ liệu OHLCV từ Binance Futures.
        Trả về DataFrame với columns: open/high/low/close/volume.
        Xử lý đúng số thập phân, KHÔNG làm tròn.
        """
        symbol = symbol.upper()

        # ── Kiểm tra cache ──────────────────────────────────────────
        if use_cache:
            cached = await _cache.get(symbol, interval, suffix="klines")
            if cached is not None:
                return pd.DataFrame(cached)

        # ── Gọi API ────────────────────────────────────────────────
        async with _semaphore:
            await self._ensure_session()
            await asyncio.sleep(config.REQUEST_DELAY_SECONDS)

            url    = f"{self.BASE_URL}/fapi/v1/klines"
            params = {"symbol": symbol, "interval": interval, "limit": limit}

            try:
                async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise ValueError(f"Binance API lỗi {resp.status}: {text}")
                    raw = await resp.json()
            except asyncio.TimeoutError:
                raise ConnectionError("Timeout khi kết nối Binance API")

        df = self._parse_klines(raw)

        # ── Lưu cache ──────────────────────────────────────────────
        if use_cache:
            await _cache.set(symbol, interval, df.to_dict("records"), suffix="klines")

        return df

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_klines(raw: list) -> pd.DataFrame:
        """
        Parse dữ liệu thô từ Binance.
        Dùng str -> Decimal-safe float để giữ đủ độ chính xác.
        """
        columns = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_volume", "taker_buy_quote_volume", "ignore",
        ]
        df = pd.DataFrame(raw, columns=columns)

        # Chuyển kiểu – dùng float64, KHÔNG làm tròn
        for col in ["open", "high", "low", "close", "volume",
                    "quote_volume", "taker_buy_volume", "taker_buy_quote_volume"]:
            df[col] = df[col].apply(lambda x: float(str(x)))

        df["open_time"]  = pd.to_datetime(df["open_time"],  unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
        df["trades"]     = df["trades"].astype(int)

        df = df.sort_values("open_time").reset_index(drop=True)
        return df

    # ------------------------------------------------------------------
    async def get_ticker_price(self, symbol: str) -> float:
        """Giá hiện tại từ ticker – cache ngắn 10 giây."""
        cached = await _cache.get(symbol, "ticker", suffix="price")
        if cached is not None:
            return float(cached)

        async with _semaphore:
            await self._ensure_session()
            url    = f"{self.BASE_URL}/fapi/v1/ticker/price"
            params = {"symbol": symbol.upper()}
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()

        price = float(str(data["price"]))
        # TTL ngắn cho ticker
        _cache._store[_cache._make_key(symbol, "ticker", "price")] = {
            "data": price, "ts": __import__("time").time(), "ttl": 10
        } if hasattr(_cache, "_store") else None

        return price

    # ------------------------------------------------------------------
    async def validate_symbol(self, symbol: str) -> bool:
        """Kiểm tra symbol có tồn tại trên Binance Futures không."""
        async with _semaphore:
            await self._ensure_session()
            url = f"{self.BASE_URL}/fapi/v1/exchangeInfo"
            async with self.session.get(url) as resp:
                data = await resp.json()

        symbols = {s["symbol"] for s in data.get("symbols", [])}
        return symbol.upper() in symbols


# Singleton
fetcher = DataFetcher()