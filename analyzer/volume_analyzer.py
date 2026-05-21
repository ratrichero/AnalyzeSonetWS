"""Nhóm 4 – Khối lượng (Volume)"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from analyzer.indicators import volume_sma, obv, vwap, cmf


@dataclass
class VolumeResult:
    score: float
    signal: str
    details: dict = field(default_factory=dict)
    summary: str = ""


def analyze_volume(df: pd.DataFrame) -> VolumeResult:
    score   = 0.0
    details = {}

    # ── Volume vs MA ───────────────────────────────────────────────
    vol_last = float(df["volume"].iloc[-1])
    vol_ma20 = float(volume_sma(df, 20).iloc[-1])
    vol_ratio = vol_last / vol_ma20 if vol_ma20 > 0 else 1.0

    close_chg = float(df["close"].iloc[-1]) - float(df["close"].iloc[-2])
    is_up_candle = close_chg > 0

    vol_score = 0.0
    if vol_ratio > 2.0:
        vol_score = 0.8 if is_up_candle else -0.8
    elif vol_ratio > 1.5:
        vol_score = 0.5 if is_up_candle else -0.5
    elif vol_ratio > 1.0:
        vol_score = 0.2 if is_up_candle else -0.2
    else:
        vol_score = 0.0   # volume thấp – tín hiệu yếu

    details["volume"] = {
        "current": round(vol_last, 2),
        "ma20":    round(vol_ma20, 2),
        "ratio":   round(vol_ratio, 3),
        "score":   round(vol_score, 3),
        "note":    (f"Vol={vol_ratio:.2f}x MA20, "
                    f"{'🟢 Bullish surge' if vol_ratio > 1.5 and is_up_candle else '🔴 Bearish surge' if vol_ratio > 1.5 else '→ Bình thường'}"),
    }
    score += vol_score * 0.30

    # ── OBV ────────────────────────────────────────────────────────
    obv_series = obv(df)
    obv_last   = float(obv_series.iloc[-1])
    obv_ema    = float(obv_series.ewm(span=20, adjust=False).mean().iloc[-1])

    obv_score  = 0.3 if obv_last > obv_ema else -0.3
    # OBV trend (5 nến)
    obv_slope = float(obv_series.diff().tail(5).mean())
    if obv_slope > 0: obv_score += 0.2
    else:             obv_score -= 0.2
    obv_score = max(-1.0, min(1.0, obv_score))

    details["obv"] = {
        "value": round(obv_last, 2),
        "ema20": round(obv_ema, 2),
        "slope": round(obv_slope, 2),
        "score": round(obv_score, 3),
        "note":  f"OBV {'>' if obv_last > obv_ema else '<'} EMA20, Slope={'↑' if obv_slope > 0 else '↓'}",
    }
    score += obv_score * 0.30

    # ── VWAP ───────────────────────────────────────────────────────
    vwap_val  = float(vwap(df).iloc[-1])
    close_now = float(df["close"].iloc[-1])
    vwap_dist = (close_now - vwap_val) / vwap_val * 100

    vwap_score = 0.4 if close_now > vwap_val else -0.4
    details["vwap"] = {
        "value":    round(vwap_val, 8),
        "distance": round(vwap_dist, 4),
        "score":    round(vwap_score, 3),
        "note":     f"Giá {'trên' if close_now > vwap_val else 'dưới'} VWAP ({vwap_dist:+.2f}%)",
    }
    score += vwap_score * 0.20

    # ── CMF ────────────────────────────────────────────────────────
    cmf_val  = float(cmf(df, 20).iloc[-1])
    cmf_score = cmf_val * 2   # CMF range ~[-1, 1]
    cmf_score = max(-1.0, min(1.0, cmf_score))

    details["cmf"] = {
        "value": round(cmf_val, 4),
        "score": round(cmf_score, 3),
        "note":  f"CMF={cmf_val:.4f} – {'Tiền vào' if cmf_val > 0 else 'Tiền ra'}",
    }
    score += cmf_score * 0.20

    score = max(-1.0, min(1.0, score))
    if score > 0.2:    signal = "BULLISH"
    elif score < -0.2: signal = "BEARISH"
    else:              signal = "NEUTRAL"

    summary = _build_summary(signal, score, details)
    return VolumeResult(score=round(score, 4), signal=signal,
                        details=details, summary=summary)


def _build_summary(signal, score, details):
    lines = [f"📊 *Khối lượng:* {signal} (Score: {score:+.2f})"]
    lines.append(f"  • {details['volume']['note']}")
    lines.append(f"  • OBV: {details['obv']['note']}")
    lines.append(f"  • {details['vwap']['note']}")
    lines.append(f"  • {details['cmf']['note']}")
    return "\n".join(lines)