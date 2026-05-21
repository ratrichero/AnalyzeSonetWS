"""Nhóm 3 – Biến động (Volatility)"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from analyzer.indicators import (
    atr, bollinger_bands, keltner_channels, squeeze_momentum
)


@dataclass
class VolatilityResult:
    score: float
    signal: str
    atr_value: float
    atr_pct: float          # ATR% = ATR / close
    bb_width: float
    is_squeeze: bool
    details: dict = field(default_factory=dict)
    summary: str = ""


def analyze_volatility(df: pd.DataFrame) -> VolatilityResult:
    close = df["close"].iloc[-1]
    score   = 0.0
    details = {}

    # ── ATR ────────────────────────────────────────────────────────
    atr14    = atr(df, 14)
    atr_last = float(atr14.iloc[-1])
    atr_pct  = atr_last / close * 100

    # ATR% so với trung bình 20 nến → biến động đang tăng/giảm
    atr_avg  = float(atr14.tail(20).mean())
    atr_ratio = atr_last / atr_avg if atr_avg > 0 else 1.0

    details["atr"] = {
        "value":   round(atr_last, 8),
        "pct":     round(atr_pct, 4),
        "ratio":   round(atr_ratio, 3),
        "note":    (f"ATR={atr_last:.8g} ({atr_pct:.2f}% giá), "
                    f"{'↑ tăng mạnh' if atr_ratio > 1.3 else '↓ thấp' if atr_ratio < 0.7 else '→ bình thường'}"),
    }

    # ── Bollinger Bands ────────────────────────────────────────────
    bb_upper, bb_mid, bb_lower = bollinger_bands(df, 20, 2.0)
    bb_upper_l = float(bb_upper.iloc[-1])
    bb_lower_l = float(bb_lower.iloc[-1])
    bb_mid_l   = float(bb_mid.iloc[-1])
    bb_width   = (bb_upper_l - bb_lower_l) / bb_mid_l * 100  # %

    # %B = vị trí giá trong BB
    bb_pct_b   = (close - bb_lower_l) / (bb_upper_l - bb_lower_l) if (bb_upper_l - bb_lower_l) > 0 else 0.5

    bb_score = 0.0
    if bb_pct_b > 0.9:    bb_score = -0.6  # gần upper – có thể đảo chiều
    elif bb_pct_b < 0.1:  bb_score =  0.6  # gần lower
    elif bb_pct_b > 0.5:  bb_score =  0.3  # nửa trên
    else:                 bb_score = -0.3

    details["bollinger"] = {
        "upper": round(bb_upper_l, 8),
        "mid":   round(bb_mid_l,   8),
        "lower": round(bb_lower_l, 8),
        "width_pct": round(bb_width, 4),
        "pct_b": round(bb_pct_b, 4),
        "score": round(bb_score, 3),
        "note":  f"BB Width={bb_width:.2f}%, %B={bb_pct_b:.2f}",
    }
    score += bb_score * 0.40

    # ── Squeeze ────────────────────────────────────────────────────
    kc_upper, _, kc_lower = keltner_channels(df, 20, 14, 1.5)
    is_squeeze = bool(
        (bb_upper.iloc[-1] < kc_upper.iloc[-1]) and
        (bb_lower.iloc[-1] > kc_lower.iloc[-1])
    )

    sq_mom = squeeze_momentum(df)
    sq_last = float(sq_mom.iloc[-1])
    sq_prev = float(sq_mom.iloc[-2])

    details["squeeze"] = {
        "active":  is_squeeze,
        "momentum": round(sq_last, 8),
        "note": (f"Squeeze {'ON 🔴' if is_squeeze else 'OFF 🟢'}, "
                 f"Momentum {'↑' if sq_last > sq_prev else '↓'} = {sq_last:.8g}"),
    }
    if is_squeeze:
        score += 0.3 if sq_last > 0 else -0.3
    else:
        score += 0.2 if sq_last > sq_prev else -0.2

    score = max(-1.0, min(1.0, score))
    if score > 0.2:    signal = "BULLISH"
    elif score < -0.2: signal = "BEARISH"
    else:              signal = "NEUTRAL"

    summary = _build_summary(signal, score, details, is_squeeze)
    return VolatilityResult(
        score=round(score, 4), signal=signal,
        atr_value=atr_last, atr_pct=round(atr_pct, 6),
        bb_width=round(bb_width, 4), is_squeeze=is_squeeze,
        details=details, summary=summary,
    )


def _build_summary(signal, score, details, is_squeeze):
    lines = [f"🌊 *Biến động:* {signal} (Score: {score:+.2f})"]
    lines.append(f"  • {details['atr']['note']}")
    lines.append(f"  • {details['bollinger']['note']}")
    lines.append(f"  • {details['squeeze']['note']}")
    return "\n".join(lines)