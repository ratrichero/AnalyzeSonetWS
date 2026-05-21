"""
Facade chính – gọi từ Telegram bot.
KHÔNG import các module con ở top-level để tránh circular import.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def analyze_single(
    symbol: str,
    timeframe: str,
    use_cache: bool = True,
):
    """Phân tích một symbol trên một timeframe."""
    # Import bên trong function – tránh circular import
    from analyzer.data_fetcher import fetcher
    from analyzer.trend_analyzer import analyze_trend
    from analyzer.momentum_analyzer import analyze_momentum
    from analyzer.volatility_analyzer import analyze_volatility
    from analyzer.volume_analyzer import analyze_volume
    from analyzer.sr_analyzer import analyze_sr
    from analyzer.report_generator import generate_report

    df = await fetcher.get_klines(symbol, timeframe, use_cache=use_cache)

    trend      = analyze_trend(df)
    momentum   = analyze_momentum(df)
    volatility = analyze_volatility(df)
    volume     = analyze_volume(df)
    sr         = analyze_sr(df)

    return generate_report(
        symbol, timeframe, df,
        trend, momentum, volatility, volume, sr
    )


async def analyze_multi_timeframe(
    symbol: str,
    use_cache: bool = True,
):
    """Phân tích đồng thời tất cả timeframe → MTF Report."""
    from config import config
    from analyzer.report_generator import generate_mtf_report

    tasks = {
        tf: asyncio.create_task(
            analyze_single(symbol, tf, use_cache=use_cache)
        )
        for tf in config.TIMEFRAMES
    }

    reports = {}
    for tf, task in tasks.items():
        try:
            reports[tf] = await task
        except Exception as e:
            logger.error(f"Lỗi phân tích {symbol} {tf}: {e}")

    if not reports:
        raise ValueError(f"Không thể phân tích {symbol}")

    return generate_mtf_report(symbol, reports)