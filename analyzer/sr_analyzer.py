"""Nhóm 5 – Hỗ trợ/Kháng cự (S/R)"""

import pandas as pd
from dataclasses import dataclass, field
from typing import List
from analyzer.indicators import pivot_points, find_key_levels, fibonacci_levels


@dataclass
class SRResult:
    score: float
    signal: str
    nearest_support: float
    nearest_resistance: float
    key_levels: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)
    summary: str = ""


def analyze_sr(df: pd.DataFrame) -> SRResult:
    close   = float(df["close"].iloc[-1])
    score   = 0.0
    details = {}

    # ── Pivot Points ───────────────────────────────────────────────
    pivots = pivot_points(df)
    details["pivots"] = {k: round(v, 8) for k, v in pivots.items()}

    # Vị trí giá so với pivot
    p = pivots["P"]
    if close > pivots.get("R2", p): pivot_score = -0.8
    elif close > pivots.get("R1", p): pivot_score = -0.3
    elif close > p:                   pivot_score =  0.3
    elif close > pivots.get("S1", p): pivot_score = -0.1
    elif close > pivots.get("S2", p): pivot_score = -0.5
    else:                             pivot_score = -0.8
    score += pivot_score * 0.30

    # ── Key Levels ─────────────────────────────────────────────────
    key = find_key_levels(df, lookback=60)
    resistances = key["resistance"]
    supports    = key["support"]

    # Tìm gần nhất
    near_res = min(resistances, key=lambda x: abs(x - close)) if resistances else close * 1.02
    near_sup = min(supports,    key=lambda x: abs(x - close)) if supports else close * 0.98

    dist_res = (near_res - close) / close * 100
    dist_sup = (close - near_sup) / close * 100

    sr_score = 0.0
    if dist_sup > 0 and dist_res > 0:
        ratio = dist_sup / (dist_sup + dist_res)
        sr_score = (0.5 - ratio) * 2   # gần support → bullish

    details["key_levels"] = {
        "resistance": [round(r, 8) for r in resistances],
        "support":    [round(s, 8) for s in supports],
        "near_resistance": round(near_res, 8),
        "near_support":    round(near_sup, 8),
        "dist_resistance": round(dist_res, 4),
        "dist_support":    round(dist_sup, 4),
        "note": (f"Gần nhất – Kháng cự: {near_res:.8g} ({dist_res:+.2f}%), "
                 f"Hỗ trợ: {near_sup:.8g} (-{dist_sup:.2f}%)"),
    }
    score += sr_score * 0.35

    # ── Fibonacci ──────────────────────────────────────────────────
    fibs    = fibonacci_levels(df, lookback=100)
    fib_lvls = sorted(fibs.values())

    # Tìm Fib gần nhất bên dưới và bên trên
    below = [f for f in fib_lvls if f <= close]
    above = [f for f in fib_lvls if f > close]
    fib_sup = max(below) if below else fib_lvls[0]
    fib_res = min(above) if above else fib_lvls[-1]
    fib_dist_sup = (close - fib_sup) / close * 100
    fib_dist_res = (fib_res - close) / close * 100

    fib_score = (fib_dist_res - fib_dist_sup) / (fib_dist_res + fib_dist_sup + 1e-10) * (-1)
    fib_score = max(-1.0, min(1.0, fib_score))

    details["fibonacci"] = {
        "levels": {k: round(v, 8) for k, v in fibs.items()},
        "fib_support":    round(fib_sup, 8),
        "fib_resistance": round(fib_res, 8),
        "note": (f"Fib hỗ trợ: {fib_sup:.8g} (-{fib_dist_sup:.2f}%), "
                 f"Fib kháng cự: {fib_res:.8g} (+{fib_dist_res:.2f}%)"),
    }
    score += fib_score * 0.35

    # ── Tổng hợp ───────────────────────────────────────────────────
    score = max(-1.0, min(1.0, score))
    if score > 0.15:    signal = "BULLISH"
    elif score < -0.15: signal = "BEARISH"
    else:               signal = "NEUTRAL"

    key_levels = {
        "resistance": details["key_levels"]["resistance"],
        "support":    details["key_levels"]["support"],
        "pivots":     details["pivots"],
        "fibonacci":  details["fibonacci"]["levels"],
    }

    summary = _build_summary(signal, score, details)
    return SRResult(
        score=round(score, 4), signal=signal,
        nearest_support=near_sup, nearest_resistance=near_res,
        key_levels=key_levels, details=details, summary=summary,
    )


def _build_summary(signal, score, details):
    lines = [f"🎯 *Hỗ trợ/Kháng cự:* {signal} (Score: {score:+.2f})"]
    lines.append(f"  • {details['key_levels']['note']}")
    lines.append(f"  • Pivot P={details['pivots']['P']:.8g}")
    lines.append(f"  • {details['fibonacci']['note']}")
    return "\n".join(lines)