"""
Tính toán tất cả indicators cần thiết cho 5 nhóm phân tích.
Dùng pandas thuần + numpy – tránh phụ thuộc thư viện tính indicator
để có thể kiểm soát độ chính xác số thập phân.
"""

import numpy as np
import pandas as pd
from typing import Tuple


# ══════════════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════════════

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()

def _rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothed MA – dùng cho RSI, ATR."""
    alpha  = 1 / period
    result = series.ewm(alpha=alpha, adjust=False).mean()
    return result


# ══════════════════════════════════════════════════════════════════════
# NHÓM 1 – XU HƯỚNG
# ══════════════════════════════════════════════════════════════════════

def ema(df: pd.DataFrame, period: int) -> pd.Series:
    return _ema(df["close"], period)

def sma(df: pd.DataFrame, period: int) -> pd.Series:
    return _sma(df["close"], period)

def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Trả về (macd_line, signal_line, histogram)."""
    ema_fast   = _ema(df["close"], fast)
    ema_slow   = _ema(df["close"], slow)
    macd_line  = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram

def adx(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Trả về (ADX, +DI, -DI)."""
    high, low, close = df["high"], df["low"], df["close"]

    tr1  = high - low
    tr2  = (high - close.shift(1)).abs()
    tr3  = (low  - close.shift(1)).abs()
    tr   = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    dm_pos = high - high.shift(1)
    dm_neg = low.shift(1) - low
    dm_pos = dm_pos.where((dm_pos > dm_neg) & (dm_pos > 0), 0.0)
    dm_neg = dm_neg.where((dm_neg > dm_pos) & (dm_neg > 0), 0.0)

    atr14   = _rma(tr,     period)
    di_pos  = 100 * _rma(dm_pos, period) / atr14
    di_neg  = 100 * _rma(dm_neg, period) / atr14

    dx      = 100 * (di_pos - di_neg).abs() / (di_pos + di_neg)
    adx_val = _rma(dx, period)
    return adx_val, di_pos, di_neg

def ichimoku(df: pd.DataFrame) -> dict:
    high, low = df["high"], df["low"]
    tenkan  = (high.rolling(9).max()  + low.rolling(9).min())  / 2
    kijun   = (high.rolling(26).max() + low.rolling(26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    chikou  = df["close"].shift(-26)
    return {
        "tenkan": tenkan, "kijun": kijun,
        "senkou_a": senkou_a, "senkou_b": senkou_b,
        "chikou": chikou,
    }


# ══════════════════════════════════════════════════════════════════════
# NHÓM 2 – ĐỘNG LƯỢNG
# ══════════════════════════════════════════════════════════════════════

def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta  = df["close"].diff()
    gain   = delta.where(delta > 0, 0.0)
    loss   = (-delta).where(delta < 0, 0.0)
    avg_g  = _rma(gain, period)
    avg_l  = _rma(loss, period)
    rs     = avg_g / avg_l
    return 100 - (100 / (1 + rs))

def stochastic(
    df: pd.DataFrame,
    k_period: int = 14,
    d_period: int  = 3,
) -> Tuple[pd.Series, pd.Series]:
    low_min  = df["low"].rolling(k_period).min()
    high_max = df["high"].rolling(k_period).max()
    k = 100 * (df["close"] - low_min) / (high_max - low_min)
    d = _sma(k, d_period)
    return k, d

def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    tp      = (df["high"] + df["low"] + df["close"]) / 3
    ma      = _sma(tp, period)
    mad     = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    return (tp - ma) / (0.015 * mad)

def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_max = df["high"].rolling(period).max()
    low_min  = df["low"].rolling(period).min()
    return -100 * (high_max - df["close"]) / (high_max - low_min)


# ══════════════════════════════════════════════════════════════════════
# NHÓM 3 – BIẾN ĐỘNG
# ══════════════════════════════════════════════════════════════════════

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift(1)).abs()
    tr3 = (df["low"]  - df["close"].shift(1)).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return _rma(tr, period)

def bollinger_bands(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2.0,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    mid   = _sma(df["close"], period)
    std   = df["close"].rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower

def keltner_channels(
    df: pd.DataFrame,
    ema_period: int = 20,
    atr_period: int = 14,
    mult: float     = 1.5,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    mid   = _ema(df["close"], ema_period)
    atr14 = atr(df, atr_period)
    return mid + mult * atr14, mid, mid - mult * atr14

def squeeze_momentum(df: pd.DataFrame) -> pd.Series:
    """
    LazyBear Squeeze Momentum.
    Trả về histogram (dương = bullish momentum, âm = bearish).
    """
    bb_upper, bb_mid, bb_lower = bollinger_bands(df, 20, 2.0)
    kc_upper, kc_mid, kc_lower = keltner_channels(df, 20, 14, 1.5)

    # Squeeze ON = BB inside KC
    # squeeze = (bb_upper < kc_upper) & (bb_lower > kc_lower)

    # Momentum
    high_max = df["high"].rolling(20).max()
    low_min  = df["low"].rolling(20).min()
    delta    = df["close"] - (high_max + low_min) / 2
    mom      = delta.rolling(20).apply(
        lambda x: np.polyfit(np.arange(len(x)), x, 1)[0], raw=True
    )
    return mom


# ══════════════════════════════════════════════════════════════════════
# NHÓM 4 – KHỐI LƯỢNG
# ══════════════════════════════════════════════════════════════════════

def volume_sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    return _sma(df["volume"], period)

def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()

def vwap(df: pd.DataFrame) -> pd.Series:
    tp     = (df["high"] + df["low"] + df["close"]) / 3
    cum_tv = (tp * df["volume"]).cumsum()
    cum_v  = df["volume"].cumsum()
    return cum_tv / cum_v

def cmf(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Chaikin Money Flow."""
    hl    = df["high"] - df["low"]
    mfm   = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl.replace(0, np.nan)
    mfv   = mfm * df["volume"]
    return mfv.rolling(period).sum() / df["volume"].rolling(period).sum()


# ══════════════════════════════════════════════════════════════════════
# NHÓM 5 – HỖ TRỢ / KHÁNG CỰ
# ══════════════════════════════════════════════════════════════════════

def pivot_points(df: pd.DataFrame) -> dict:
    """Classic Pivot Points dựa trên nến cuối cùng."""
    last = df.iloc[-2]       # dùng nến đã đóng
    h, l, c = last["high"], last["low"], last["close"]
    p  = (h + l + c) / 3
    r1 = 2 * p - l
    s1 = 2 * p - h
    r2 = p + (h - l)
    s2 = p - (h - l)
    r3 = h + 2 * (p - l)
    s3 = l - 2 * (h - p)
    return {"P": p, "R1": r1, "R2": r2, "R3": r3,
            "S1": s1, "S2": s2, "S3": s3}

def find_key_levels(df: pd.DataFrame, lookback: int = 50, tolerance: float = 0.002) -> dict:
    """
    Tìm vùng hỗ trợ/kháng cự quan trọng dựa trên swing high/low.
    tolerance: khoảng cách tính là "cùng vùng" (0.2% mặc định).
    """
    recent = df.tail(lookback)
    highs  = recent["high"].values
    lows   = recent["low"].values

    def cluster(prices, tol):
        levels, seen = [], set()
        for p in sorted(prices, reverse=True):
            key = round(p / (p * tol + 1e-20))
            if key not in seen:
                seen.add(key)
                levels.append(float(p))
        return levels[:5]

    resistances = cluster(highs, tolerance)
    supports    = cluster(lows,  tolerance)
    return {"resistance": sorted(resistances, reverse=True),
            "support":    sorted(supports)}

def fibonacci_levels(df: pd.DataFrame, lookback: int = 100) -> dict:
    recent  = df.tail(lookback)
    high    = float(recent["high"].max())
    low     = float(recent["low"].min())
    diff    = high - low
    ratios  = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    levels  = {f"fib_{r}": high - diff * r for r in ratios}
    return levels