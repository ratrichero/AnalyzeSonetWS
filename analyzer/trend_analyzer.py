"""Nhóm 1 – Xu hướng (Trend)"""

import pandas as pd
from dataclasses import dataclass, field
from typing import Tuple

# Chỉ import từ indicators – KHÔNG import từ analyzer package
from analyzer.indicators import (
    ema, sma, macd, adx, ichimoku
)


@dataclass
class TrendResult:
    score: float
    signal: str
    details: dict = field(default_factory=dict)
    summary: str = ""


def analyze_trend(df: pd.DataFrame) -> TrendResult:
    close = df["close"]
    last  = float(close.iloc[-1])
    score = 0.0
    details = {}

    # ── EMA Cloud (20/50/200) ──────────────────────────────────────
    e20  = float(ema(df, 20).iloc[-1])
    e50  = float(ema(df, 50).iloc[-1])
    e200 = float(ema(df, 200).iloc[-1])

    ema_score = 0.0
    if last > e20:  ema_score += 0.3
    else:           ema_score -= 0.3
    if last > e50:  ema_score += 0.3
    else:           ema_score -= 0.3
    if last > e200: ema_score += 0.4
    else:           ema_score -= 0.4

    if e20 > e50 > e200:   ema_score = min(ema_score + 0.2, 1.0)
    elif e20 < e50 < e200: ema_score = max(ema_score - 0.2, -1.0)

    details["ema"] = {
        "ema20": e20, "ema50": e50, "ema200": e200,
        "score": round(ema_score, 3),
        "note":  (f"Giá {'>' if last > e20 else '<'} EMA20, "
                  f"{'>' if last > e50 else '<'} EMA50, "
                  f"{'>' if last > e200 else '<'} EMA200"),
    }
    score += ema_score * 0.35

    # ── MACD ───────────────────────────────────────────────────────
    macd_line, sig_line, hist = macd(df)
    macd_score = 0.0
    if float(macd_line.iloc[-1]) > float(sig_line.iloc[-1]): macd_score += 0.5
    else:                                                      macd_score -= 0.5
    if float(hist.iloc[-1]) > float(hist.iloc[-2]):           macd_score += 0.3
    else:                                                      macd_score -= 0.3
    if float(macd_line.iloc[-1]) > 0:                         macd_score += 0.2
    else:                                                      macd_score -= 0.2
    macd_score = max(-1.0, min(1.0, macd_score))

    details["macd"] = {
        "macd":      round(float(macd_line.iloc[-1]), 8),
        "signal":    round(float(sig_line.iloc[-1]),  8),
        "histogram": round(float(hist.iloc[-1]),      8),
        "score":     round(macd_score, 3),
        "note": (f"MACD {'>' if float(macd_line.iloc[-1]) > float(sig_line.iloc[-1]) else '<'} Signal, "
                 f"Histogram {'tăng' if float(hist.iloc[-1]) > float(hist.iloc[-2]) else 'giảm'}"),
    }
    score += macd_score * 0.30

    # ── ADX ────────────────────────────────────────────────────────
    adx_val, di_pos, di_neg = adx(df)
    adx_last = float(adx_val.iloc[-1])
    di_p     = float(di_pos.iloc[-1])
    di_n     = float(di_neg.iloc[-1])

    adx_score = 0.0
    if adx_last > 25:
        adx_score = 0.5 if di_p > di_n else -0.5
        if adx_last > 40:
            adx_score *= 1.4
    adx_score = max(-1.0, min(1.0, adx_score))

    details["adx"] = {
        "adx":      round(adx_last, 2),
        "di_plus":  round(di_p, 2),
        "di_minus": round(di_n, 2),
        "score":    round(adx_score, 3),
        "note": (f"ADX={adx_last:.1f} – "
                 f"{'Xu hướng mạnh' if adx_last > 25 else 'Sideway'}, "
                 f"+DI {'>' if di_p > di_n else '<'} -DI"),
    }
    score += adx_score * 0.20

    # ── Ichimoku ───────────────────────────────────────────────────
    ichi      = ichimoku(df)
    tenkan_l  = float(ichi["tenkan"].iloc[-1])
    kijun_l   = float(ichi["kijun"].iloc[-1])
    senkou_a  = float(ichi["senkou_a"].iloc[-1])
    senkou_b  = float(ichi["senkou_b"].iloc[-1])
    cloud_top = max(senkou_a, senkou_b)
    cloud_bot = min(senkou_a, senkou_b)

    ichi_score = 0.0
    if last > cloud_top:   ichi_score += 0.5
    elif last < cloud_bot: ichi_score -= 0.5
    if tenkan_l > kijun_l: ichi_score += 0.3
    else:                  ichi_score -= 0.3
    ichi_score = max(-1.0, min(1.0, ichi_score))

    details["ichimoku"] = {
        "tenkan":    round(tenkan_l,  8),
        "kijun":     round(kijun_l,   8),
        "cloud_top": round(cloud_top, 8),
        "cloud_bot": round(cloud_bot, 8),
        "score":     round(ichi_score, 3),
        "note": (f"Giá {'trên mây' if last > cloud_top else 'dưới mây' if last < cloud_bot else 'trong mây'}, "
                 f"Tenkan {'>' if tenkan_l > kijun_l else '<'} Kijun"),
    }
    score += ichi_score * 0.15

    # ── Tổng hợp ───────────────────────────────────────────────────
    score = max(-1.0, min(1.0, score))
    if score > 0.2:    signal = "BULLISH"
    elif score < -0.2: signal = "BEARISH"
    else:              signal = "NEUTRAL"

    summary = _build_summary(signal, score, details)
    return TrendResult(
        score=round(score, 4),
        signal=signal,
        details=details,
        summary=summary,
    )


def _build_summary(signal: str, score: float, details: dict) -> str:
    lines = [f"📈 *Xu hướng:* {signal} (Score: {score:+.2f})"]
    lines.append(f"  • EMA: {details['ema']['note']}")
    lines.append(f"  • MACD: {details['macd']['note']}")
    lines.append(f"  • ADX: {details['adx']['note']}")
    lines.append(f"  • Ichimoku: {details['ichimoku']['note']}")
    return "\n".join(lines)