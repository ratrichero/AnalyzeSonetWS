"""
Tổng hợp kết quả 5 nhóm → báo cáo + khuyến nghị giao dịch.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List
from config import config


# ══════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════

def _fmt(v: float) -> str:
    if v == 0:        return "0"
    if v >= 10000:    return f"{v:,.2f}"
    if v >= 1000:     return f"{v:.3f}"
    if v >= 100:      return f"{v:.4f}"
    if v >= 1:        return f"{v:.5f}"
    if v >= 0.01:     return f"{v:.6f}"
    if v >= 0.0001:   return f"{v:.8f}"
    return f"{v:.10g}"


def _ensure_diff(ref: float, target: float, min_diff: float, go_up: bool) -> float:
    return max(target, ref + min_diff) if go_up else min(target, ref - min_diff)


def _calc_rr(entry: float, sl: float, tp: float) -> float:
    risk   = abs(entry - sl)
    reward = abs(tp - entry)
    return round(reward / risk, 2) if risk > 1e-12 else 0.0


# ══════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════

@dataclass
class SingleTradeSetup:
    """Setup cho 1 hướng giao dịch."""
    direction: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    rr_ratio: float
    confidence: float
    invalidation: str


@dataclass
class TradeSetup:
    """Setup tổng hợp – hỗ trợ cả directional và range."""
    direction: str
    entry: float        = 0.0
    sl: float           = 0.0
    tp1: float          = 0.0
    tp2: float          = 0.0
    rr_ratio: float     = 0.0
    confidence: float   = 0.0
    invalidation: str   = ""
    range_low: float    = 0.0
    range_high: float   = 0.0
    price_position: float = -1.0
    long_setup:  Optional[SingleTradeSetup] = None
    short_setup: Optional[SingleTradeSetup] = None
    recommended: str    = ""


@dataclass
class FullReport:
    symbol: str
    timeframe: str
    current_price: float
    trend: object
    momentum: object
    volatility: object
    volume: object
    sr: object
    composite_score: float
    trade_setup: TradeSetup
    mtf_summary: Optional[dict] = None


@dataclass
class NeutralRange:
    range_low: float
    range_high: float
    range_mid: float
    current_price: float
    price_position: float
    long_entry: float
    long_sl: float
    long_tp1: float
    long_tp2: float
    long_rr: float
    short_entry: float
    short_sl: float
    short_tp1: float
    short_tp2: float
    short_rr: float
    range_width_pct: float
    recommended: str


@dataclass
class MTFReport:
    symbol: str
    reports: dict
    consensus_score: float
    consensus_direction: str
    confidence: float
    best_timeframe: str
    trade_setup: TradeSetup
    risk_level: str
    reasons: list       = field(default_factory=list)
    checklist: list     = field(default_factory=list)
    invalidation: str   = ""
    neutral_range: Optional[NeutralRange] = None


# ══════════════════════════════════════════════════════════════════════
# S/R HELPER
# ══════════════════════════════════════════════════════════════════════

def _get_valid_sr(
    close: float,
    atr14: float,
    sr,
) -> tuple:
    """
    Tìm cặp Support/Resistance hợp lệ bao quanh giá hiện tại.

    Nguyên tắc:
    - Support  phải THẤP HƠN giá (close - min_gap)
    - Resistance phải CAO HƠN giá (close + min_gap)
    - Range phải đủ rộng: tối thiểu max(3×ATR, 1% giá)
    - Ưu tiên: key_levels → pivot → fibonacci
    - Loại duplicate trong vòng 0.1%
    - Fallback ATR×3 nếu không tìm được
    """
    # Thu thập levels theo nhóm
    key_sup  = sr.key_levels.get("support",    [])
    key_res  = sr.key_levels.get("resistance", [])
    pivots   = sr.key_levels.get("pivots",     {})
    fibs     = sr.key_levels.get("fibonacci",  {})

    piv_sup  = [v for k, v in pivots.items() if k.startswith("S")]
    piv_res  = [v for k, v in pivots.items() if k.startswith("R")]
    fib_vals = list(fibs.values())

    min_gap = close * 0.0005  # tối thiểu cách giá 0.05%

    def filter_sup(levels):
        return sorted(
            [v for v in levels if isinstance(v, (int, float))
             and v > 0 and v < close - min_gap],
            reverse=True
        )

    def filter_res(levels):
        return sorted(
            [v for v in levels if isinstance(v, (int, float))
             and v > 0 and v > close + min_gap]
        )

    # Gộp theo thứ tự ưu tiên
    all_sup = filter_sup(key_sup) + filter_sup(piv_sup) + filter_sup(fib_vals)
    all_res = filter_res(key_res) + filter_res(piv_res) + filter_res(fib_vals)

    # Loại duplicate gần nhau (trong vòng 0.1%)
    def dedupe(levels: list) -> list:
        result = []
        for v in levels:
            if not result:
                result.append(v)
            elif abs(v - result[-1]) / close > 0.001:
                result.append(v)
        return result

    all_sup = dedupe(all_sup)
    all_res = dedupe(all_res)

    # Tìm cặp S/R có range đủ rộng
    MIN_RANGE_PCT = max(atr14 / close * 3, 0.01)  # ít nhất 3×ATR hoặc 1%

    near_sup = None
    near_res = None

    for sup in all_sup[:6]:
        for res in all_res[:6]:
            if (res - sup) / close >= MIN_RANGE_PCT:
                near_sup = sup
                near_res = res
                break
        if near_sup and near_res:
            break

    # Fallback nếu không tìm được cặp hợp lệ
    if not near_sup:
        near_sup = close - atr14 * 3.0
    if not near_res:
        near_res = close + atr14 * 3.0

    # Safety check cuối
    if near_sup >= close:
        near_sup = close - atr14 * 3.0
    if near_res <= close:
        near_res = close + atr14 * 3.0

    # Rebuild lists tương ứng với cặp đã chọn
    final_sup = [v for v in all_sup if v <= near_sup + close * 0.002]
    final_res = [v for v in all_res if v >= near_res - close * 0.002]

    return near_sup, near_res, final_sup, final_res


# ══════════════════════════════════════════════════════════════════════
# SINGLE TIMEFRAME REPORT
# ══════════════════════════════════════════════════════════════════════

def generate_report(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    trend, momentum, volatility, volume, sr
) -> FullReport:
    from analyzer.indicators import atr as calc_atr

    close = float(df["close"].iloc[-1])
    atr14 = float(calc_atr(df, 14).iloc[-1])

    # ── Composite Score ────────────────────────────────────────
    weights = {
        "trend":      0.30,
        "momentum":   0.25,
        "volatility": 0.15,
        "volume":     0.20,
        "sr":         0.10,
    }
    
    # Đơn giản hóa - tính trực tiếp
    composite = (
        trend.score      * weights["trend"] +
        momentum.score   * weights["momentum"] +
        volatility.score * weights["volatility"] +
        volume.score     * weights["volume"] +
        sr.score         * weights["sr"]
    )
    composite = round(max(-1.0, min(1.0, composite)), 4)

    # ── Xác định hướng ────────────────────────────────────────
    if composite > 0.25:    direction = "LONG"
    elif composite < -0.25: direction = "SHORT"
    else:                   direction = "NEUTRAL"

    # ── Trade Setup ────────────────────────────────────────────
    if direction == "NEUTRAL":
        setup = _calc_neutral_single_setup(close, atr14, sr, composite)
    else:
        setup = _calc_directional_setup(direction, close, atr14, sr, composite)

    return FullReport(
        symbol=symbol, timeframe=timeframe,
        current_price=close,
        trend=trend, momentum=momentum,
        volatility=volatility, volume=volume, sr=sr,
        composite_score=composite,
        trade_setup=setup,
    )


def _calc_directional_setup(
    direction: str,
    close: float,
    atr14: float,
    sr,
    composite: float,
) -> TradeSetup:
    """LONG/SHORT rõ ràng – Entry pullback, SL/TP theo S/R + R/R."""
    RR_MIN     = getattr(config, 'RR_MIN', 2.0)
    RR_CAP     = getattr(config, 'RR_CAP', 8.0)
    min_diff   = atr14 * 0.05
    confidence = min(100.0, abs(composite) * 100 * 1.5)

    near_sup, near_res, all_sup, all_res = _get_valid_sr(close, atr14, sr)

    valid_sup = near_sup > 0 and near_sup < close * 0.9995
    valid_res = near_res > 0 and near_res > close * 1.0005

    if direction == "LONG":
        # Entry: pullback về gần support
        if valid_sup:
            dist_pct = (close - near_sup) / close
            if dist_pct <= 0.012:
                entry = near_sup * 1.002
            elif dist_pct <= 0.025:
                entry = close - (close - near_sup) * 0.5
            elif dist_pct <= 0.05:
                entry = close - atr14 * 0.5
            else:
                entry = close - atr14 * 0.3
        else:
            entry = close - atr14 * 0.3

        # TP2 từ resistance
        if len(all_res) >= 2:
            tp2_target = all_res[1] * 0.997
        elif all_res:
            tp2_target = all_res[0] * 0.997
        else:
            tp2_target = entry + atr14 * RR_MIN * 1.5

        reward   = abs(tp2_target - entry)
        risk_rr  = reward / RR_MIN
        sl_rr    = entry - risk_rr
        sl_sr    = near_sup - atr14 * 0.3 if valid_sup else sl_rr
        sl       = max(sl_rr, sl_sr)
        sl       = min(sl, entry - min_diff)

        actual_risk = abs(entry - sl)
        tp1 = entry + actual_risk
        if all_res:
            tp1 = min(tp1, all_res[0] * 0.997)
        tp1 = max(tp1, entry + min_diff)
        tp2 = max(tp2_target, tp1 + min_diff)

        # Validate: SL < Entry < TP1 < TP2
        sl  = min(sl,  entry - min_diff)
        tp1 = max(tp1, entry + min_diff)
        tp2 = max(tp2, tp1   + min_diff)

        inv_level = near_sup if valid_sup else sl
        inv = f"Nến đóng cửa dưới {_fmt(inv_level)} → Long vô hiệu"

    else:  # SHORT
        if valid_res:
            dist_pct = (near_res - close) / close
            if dist_pct <= 0.012:
                entry = near_res * 0.998
            elif dist_pct <= 0.025:
                entry = close + (near_res - close) * 0.5
            elif dist_pct <= 0.05:
                entry = close + atr14 * 0.5
            else:
                entry = close + atr14 * 0.3
        else:
            entry = close + atr14 * 0.3

        if len(all_sup) >= 2:
            tp2_target = all_sup[1] * 1.003
        elif all_sup:
            tp2_target = all_sup[0] * 1.003
        else:
            tp2_target = entry - atr14 * RR_MIN * 1.5

        reward   = abs(entry - tp2_target)
        risk_rr  = reward / RR_MIN
        sl_rr    = entry + risk_rr
        sl_sr    = near_res + atr14 * 0.3 if valid_res else sl_rr
        sl       = min(sl_rr, sl_sr)
        sl       = max(sl, entry + min_diff)

        actual_risk = abs(sl - entry)
        tp1 = entry - actual_risk
        if all_sup:
            tp1 = max(tp1, all_sup[0] * 1.003)
        tp1 = min(tp1, entry - min_diff)
        tp2 = min(tp2_target, tp1 - min_diff)

        # Validate: TP2 < TP1 < Entry < SL
        sl  = max(sl,  entry + min_diff)
        tp1 = min(tp1, entry - min_diff)
        tp2 = min(tp2, tp1   - min_diff)

        inv_level = near_res if valid_res else sl
        inv = f"Nến đóng cửa trên {_fmt(inv_level)} → Short vô hiệu"

    # R/R sanity
    rr = _calc_rr(entry, sl, tp2)
    if rr > RR_CAP:
        ideal_risk = abs(tp2 - entry) / RR_CAP
        if direction == "LONG":
            sl = entry - ideal_risk
            sl = min(sl, entry - min_diff)
        else:
            sl = entry + ideal_risk
            sl = max(sl, entry + min_diff)
        rr = _calc_rr(entry, sl, tp2)

    if rr < 1.0:
        confidence = min(confidence, 20.0)
    elif rr < RR_MIN:
        confidence = min(confidence, 35.0)

    return TradeSetup(
        direction=direction,
        entry=entry, sl=sl, tp1=tp1, tp2=tp2,
        rr_ratio=round(min(rr, RR_CAP), 2),
        confidence=round(confidence, 1),
        invalidation=inv,
        range_low=near_sup if valid_sup else 0.0,
        range_high=near_res if valid_res else 0.0,
        price_position=-1.0,
    )


def _calc_neutral_single_setup(
    close: float,
    atr14: float,
    sr,
    composite: float,
) -> TradeSetup:
    """
    Range Trading – luôn đề xuất 2 setup:
    - LONG:  Limit order TẠI support, chờ giá về
    - SHORT: Limit order TẠI resistance, chờ giá lên
    - Entry KHÔNG phải giá hiện tại
    - SL = 1.5×ATR ngoài biên
    - TP1 = midpoint range (≥ R/R 1:1)
    - TP2 = biên đối diện
    """
    RR_MIN   = getattr(config, 'RR_MIN', 2.0)
    RR_CAP   = getattr(config, 'RR_CAP', 8.0)
    min_diff = atr14 * 0.05

    # ── Bước 1: Lấy S/R hợp lệ ───────────────────────────────
    near_sup, near_res, all_sup_below, all_res_above = _get_valid_sr(
        close, atr14, sr
    )

    range_width = near_res - near_sup
    range_mid   = (near_sup + near_res) / 2
    price_pos   = (
        (close - near_sup) / range_width
        if range_width > 1e-12 else 0.5
    )
    dist_to_sup = (close - near_sup) / close * 100
    dist_to_res = (near_res - close) / close * 100

    # ── Bước 2: LONG Setup ───────────────────────────────────
    long_entry = near_sup                    # Limit order TẠI support
    long_sl    = near_sup - atr14 * 1.5    # SL dưới support 1.5×ATR

    # TP2: resistance xa hơn nếu có
    long_tp2 = all_res_above[1] * 0.998 if len(all_res_above) >= 2 \
               else near_res * 0.998

    long_reward = abs(long_tp2 - long_entry)
    long_risk   = abs(long_entry - long_sl)

    # Đảm bảo R/R tối thiểu
    if long_risk > 1e-12 and (long_reward / long_risk) < RR_MIN:
        long_sl = long_entry - long_reward / RR_MIN
    long_sl   = min(long_sl, long_entry - min_diff)
    long_risk = abs(long_entry - long_sl)

    # TP1: midpoint hoặc ít nhất R/R 1:1
    long_tp1 = max(range_mid, long_entry + long_risk)
    long_tp1 = min(long_tp1, long_tp2 - min_diff)
    long_tp1 = max(long_tp1, long_entry + min_diff)

    # Validate: SL < Entry < TP1 < TP2
    long_sl  = min(long_sl,  long_entry - min_diff)
    long_tp1 = max(long_tp1, long_entry + min_diff)
    long_tp2 = max(long_tp2, long_tp1   + min_diff)

    long_rr = _calc_rr(long_entry, long_sl, long_tp2)
    if long_rr > RR_CAP:
        long_sl = long_entry - abs(long_tp2 - long_entry) / RR_CAP
        long_sl = min(long_sl, long_entry - min_diff)
        long_rr = _calc_rr(long_entry, long_sl, long_tp2)

    long_ready = dist_to_sup <= 0.5    # giá cách support ≤ 0.5%

    # ── Bước 3: SHORT Setup ──────────────────────────────────
    short_entry = near_res                   # Limit order TẠI resistance
    short_sl    = near_res + atr14 * 1.5   # SL trên resistance 1.5×ATR

    # TP2: support xa hơn nếu có
    short_tp2 = all_sup_below[1] * 1.002 if len(all_sup_below) >= 2 \
                else near_sup * 1.002

    short_reward = abs(short_entry - short_tp2)
    short_risk   = abs(short_sl - short_entry)

    if short_risk > 1e-12 and (short_reward / short_risk) < RR_MIN:
        short_sl = short_entry + short_reward / RR_MIN
    short_sl   = max(short_sl, short_entry + min_diff)
    short_risk = abs(short_sl - short_entry)

    # TP1: midpoint hoặc ít nhất R/R 1:1
    short_tp1 = min(range_mid, short_entry - short_risk)
    short_tp1 = max(short_tp1, short_tp2 + min_diff)
    short_tp1 = min(short_tp1, short_entry - min_diff)

    # Validate: TP2 < TP1 < Entry < SL
    short_sl  = max(short_sl,  short_entry + min_diff)
    short_tp1 = min(short_tp1, short_entry - min_diff)
    short_tp2 = min(short_tp2, short_tp1   - min_diff)

    short_rr = _calc_rr(short_entry, short_sl, short_tp2)
    if short_rr > RR_CAP:
        short_sl = short_entry + abs(short_entry - short_tp2) / RR_CAP
        short_sl = max(short_sl, short_entry + min_diff)
        short_rr = _calc_rr(short_entry, short_sl, short_tp2)

    short_ready = dist_to_res <= 0.5

    # ── Bước 4: Confidence ───────────────────────────────────
    base = 35.0
    if composite >= 0.08:       # thiên tăng
        long_conf  = min(base + composite * 60 + (1 - price_pos) * 10, 55.0)
        short_conf = min(base - composite * 20 + price_pos * 5,        45.0)
    elif composite <= -0.08:    # thiên giảm
        short_conf = min(base + abs(composite) * 60 + price_pos * 10,  55.0)
        long_conf  = min(base - abs(composite) * 20 + (1-price_pos)*5, 45.0)
    else:                       # thực sự neutral
        long_conf  = min(base + (1 - price_pos) * 15, 50.0)
        short_conf = min(base + price_pos * 15,        50.0)

    # Bonus khi giá sát biên
    if long_ready:  long_conf  = min(long_conf  + 10, 60.0)
    if short_ready: short_conf = min(short_conf + 10, 60.0)

    long_conf  = round(max(long_conf,  10.0), 1)
    short_conf = round(max(short_conf, 10.0), 1)

    # ── Bước 5: Build SingleTradeSetup ───────────────────────
    long_setup = SingleTradeSetup(
        direction="LONG",
        entry=long_entry, sl=long_sl,
        tp1=long_tp1,     tp2=long_tp2,
        rr_ratio=round(min(long_rr, RR_CAP), 2),
        confidence=long_conf,
        invalidation=f"Đóng cửa dưới {_fmt(long_sl)} → Long vô hiệu",
    )
    short_setup = SingleTradeSetup(
        direction="SHORT",
        entry=short_entry, sl=short_sl,
        tp1=short_tp1,    tp2=short_tp2,
        rr_ratio=round(min(short_rr, RR_CAP), 2),
        confidence=short_conf,
        invalidation=f"Đóng cửa trên {_fmt(short_sl)} → Short vô hiệu",
    )

    # ── Bước 6: Recommended ──────────────────────────────────
    if composite >= 0.08:    recommended = "LONG"
    elif composite <= -0.08: recommended = "SHORT"
    else:                    recommended = "BOTH"

    primary = long_setup if recommended in ("LONG", "BOTH") else short_setup

    return TradeSetup(
        direction="NEUTRAL",
        entry=primary.entry,   sl=primary.sl,
        tp1=primary.tp1,       tp2=primary.tp2,
        rr_ratio=primary.rr_ratio,
        confidence=primary.confidence,
        invalidation=primary.invalidation,
        range_low=near_sup,    range_high=near_res,
        price_position=round(price_pos, 3),
        long_setup=long_setup,
        short_setup=short_setup,
        recommended=recommended,
    )


# ══════════════════════════════════════════════════════════════════════
# MULTI TIMEFRAME REPORT
# ══════════════════════════════════════════════════════════════════════

def _calc_neutral_range_mtf(
    reports: dict,
    current_price: float,
    atr14: float,
) -> Optional[NeutralRange]:
    """MTF version: gộp S/R từ nhiều timeframe."""
    all_sup_raw = []
    all_res_raw = []

    for tf, rpt in reports.items():
        sup, res, sups, ress = _get_valid_sr(
            current_price, rpt.volatility.atr_value, rpt.sr
        )
        all_sup_raw.extend(sups)
        all_res_raw.extend(ress)
        if sup < current_price:
            all_sup_raw.append(sup)
        if res > current_price:
            all_res_raw.append(res)

    min_gap = current_price * 0.0005
    all_sup = sorted(
        set([v for v in all_sup_raw if v < current_price - min_gap and v > 0]),
        reverse=True
    )
    all_res = sorted(
        set([v for v in all_res_raw if v > current_price + min_gap and v > 0])
    )

    MIN_RANGE = max(atr14 / current_price * 3, 0.01)
    near_sup = near_res = None

    for sup in all_sup[:6]:
        for res in all_res[:6]:
            if (res - sup) / current_price >= MIN_RANGE:
                near_sup, near_res = sup, res
                break
        if near_sup:
            break

    if not near_sup:
        near_sup = current_price - atr14 * 3
    if not near_res:
        near_res = current_price + atr14 * 3

    return _build_neutral_range(near_sup, near_res, current_price, atr14, all_sup, all_res)


def _build_neutral_range(
    near_sup: float,
    near_res: float,
    current_price: float,
    atr14: float,
    all_sup: list,
    all_res: list,
) -> NeutralRange:
    RR_MIN   = getattr(config, 'RR_MIN', 2.0)
    RR_CAP   = getattr(config, 'RR_CAP', 8.0)
    min_diff = atr14 * 0.05

    range_mid       = (near_sup + near_res) / 2
    range_width_pct = (near_res - near_sup) / current_price * 100
    price_position  = (current_price - near_sup) / (near_res - near_sup)

    # Long
    long_entry = near_sup
    long_sl    = near_sup - atr14 * 1.5
    long_tp2   = all_res[1] * 0.998 if len(all_res) >= 2 else near_res * 0.998
    long_rw    = abs(long_tp2 - long_entry)
    long_risk  = abs(long_entry - long_sl)
    if long_risk > 1e-12 and long_rw / long_risk < RR_MIN:
        long_sl = long_entry - long_rw / RR_MIN
    long_sl  = min(long_sl, long_entry - min_diff)
    long_risk = abs(long_entry - long_sl)
    long_tp1 = max(range_mid, long_entry + long_risk)
    long_tp1 = min(long_tp1, long_tp2 - min_diff)
    long_tp1 = max(long_tp1, long_entry + min_diff)
    long_tp2 = max(long_tp2, long_tp1 + min_diff)

    # Short
    short_entry = near_res
    short_sl    = near_res + atr14 * 1.5
    short_tp2   = all_sup[1] * 1.002 if len(all_sup) >= 2 else near_sup * 1.002
    short_rw    = abs(short_entry - short_tp2)
    short_risk  = abs(short_sl - short_entry)
    if short_risk > 1e-12 and short_rw / short_risk < RR_MIN:
        short_sl = short_entry + short_rw / RR_MIN
    short_sl   = max(short_sl, short_entry + min_diff)
    short_risk = abs(short_sl - short_entry)
    short_tp1  = min(range_mid, short_entry - short_risk)
    short_tp1  = max(short_tp1, short_tp2 + min_diff)
    short_tp1  = min(short_tp1, short_entry - min_diff)
    short_tp2  = min(short_tp2, short_tp1 - min_diff)

    if price_position <= 0.35:   recommended = "LONG"
    elif price_position >= 0.65: recommended = "SHORT"
    else:                        recommended = "WAIT"

    return NeutralRange(
        range_low=near_sup,   range_high=near_res,
        range_mid=range_mid,  current_price=current_price,
        price_position=round(price_position, 3),
        long_entry=long_entry,  long_sl=long_sl,
        long_tp1=long_tp1,      long_tp2=long_tp2,
        long_rr=round(min(_calc_rr(long_entry, long_sl, long_tp2), RR_CAP), 2),
        short_entry=short_entry, short_sl=short_sl,
        short_tp1=short_tp1,     short_tp2=short_tp2,
        short_rr=round(min(_calc_rr(short_entry, short_sl, short_tp2), RR_CAP), 2),
        range_width_pct=round(range_width_pct, 3),
        recommended=recommended,
    )


def generate_mtf_report(symbol: str, reports: dict) -> MTFReport:
    weights = config.TIMEFRAME_WEIGHTS
    score   = sum(
        reports[tf].composite_score * weights.get(tf, 0.25)
        for tf in reports
    )
    total_w = sum(weights.get(tf, 0.25) for tf in reports)
    consensus_score = score / total_w if total_w > 0 else 0.0

    if consensus_score > 0.20:    direction = "LONG"
    elif consensus_score < -0.20: direction = "SHORT"
    else:                         direction = "NEUTRAL"

    matching = sum(
        1 for r in reports.values()
        if (direction == "LONG"    and r.composite_score > 0.10) or
           (direction == "SHORT"   and r.composite_score < -0.10) or
           (direction == "NEUTRAL" and abs(r.composite_score) <= 0.20)
    )
    confidence = matching / len(reports) * 100 if reports else 0.0

    best_tf    = max(reports, key=lambda tf: abs(reports[tf].composite_score))
    primary_tf = "4h" if "4h" in reports else best_tf
    primary    = reports[primary_tf]
    price      = primary.current_price
    atr14      = primary.volatility.atr_value

    neutral_range = None
    if direction == "NEUTRAL":
        neutral_range = _calc_neutral_range_mtf(reports, price, atr14)
        trade_setup   = _neutral_range_to_setup(neutral_range, atr14)
    else:
        trade_setup = primary.trade_setup

    return MTFReport(
        symbol=symbol, reports=reports,
        consensus_score=round(consensus_score, 4),
        consensus_direction=direction,
        confidence=round(confidence, 1),
        best_timeframe=best_tf,
        trade_setup=trade_setup,
        risk_level=_assess_risk(reports, consensus_score),
        reasons=_build_reasons(direction, reports),
        checklist=_build_checklist(direction),
        invalidation=_build_invalidation(direction, primary, neutral_range),
        neutral_range=neutral_range,
    )


def _neutral_range_to_setup(nr: NeutralRange, atr14: float) -> TradeSetup:
    min_diff = atr14 * 0.05
    if nr.recommended == "LONG":
        return TradeSetup(
            direction="NEUTRAL", recommended="LONG",
            entry=nr.long_entry,  sl=nr.long_sl,
            tp1=nr.long_tp1,      tp2=nr.long_tp2,
            rr_ratio=nr.long_rr,  confidence=45.0,
            invalidation=f"Đóng cửa dưới {_fmt(nr.long_sl)}",
            range_low=nr.range_low, range_high=nr.range_high,
            price_position=nr.price_position,
        )
    elif nr.recommended == "SHORT":
        return TradeSetup(
            direction="NEUTRAL", recommended="SHORT",
            entry=nr.short_entry, sl=nr.short_sl,
            tp1=nr.short_tp1,     tp2=nr.short_tp2,
            rr_ratio=nr.short_rr, confidence=45.0,
            invalidation=f"Đóng cửa trên {_fmt(nr.short_sl)}",
            range_low=nr.range_low, range_high=nr.range_high,
            price_position=nr.price_position,
        )
    else:
        return TradeSetup(
            direction="NEUTRAL", recommended="WAIT",
            entry=nr.current_price, sl=nr.long_sl,
            tp1=nr.range_high,      tp2=nr.range_high,
            rr_ratio=0.0,           confidence=15.0,
            invalidation="Chờ giá về biên range",
            range_low=nr.range_low, range_high=nr.range_high,
            price_position=nr.price_position,
        )


def _assess_risk(reports: dict, score: float) -> str:
    avg_vol   = float(np.mean([r.volatility.atr_pct for r in reports.values()]))
    abs_score = abs(score)
    if avg_vol > 5 or abs_score < 0.15:    return "🔴 CAO"
    elif avg_vol > 2.5 or abs_score < 0.3: return "🟡 TRUNG BÌNH"
    else:                                   return "🟢 THẤP"


def _build_reasons(direction: str, reports: dict) -> list:
    header = {
        "LONG":    "📈 Lý do LONG:",
        "SHORT":   "📉 Lý do SHORT:",
        "NEUTRAL": "↔️ Thị trường NEUTRAL – Range Trading:",
    }
    reasons = [header.get(direction, "")]
    for tf in config.TIMEFRAMES:
        if tf not in reports:
            continue
        r  = reports[tf]
        s  = r.composite_score
        em = "🟢" if s > 0.1 else "🔴" if s < -0.1 else "⚪"
        reasons.append(
            f"  {em} [{tf.upper()}] {s:+.2f} │ "
            f"Trend:{r.trend.signal[:4]} │ "
            f"Mom:{r.momentum.signal[:4]} │ "
            f"Vol:{r.volume.signal[:4]}"
        )
    return reasons


def _build_checklist(direction: str) -> list:
    base = [
        "☐ Xác nhận tín hiệu trên nến 15m trước khi vào",
        "☐ Đặt SL ngay sau khi khớp lệnh",
        "☐ Kích thước vị thế ≤ 2% tài khoản",
        "☐ Kiểm tra tin tức sắp ra",
        "☐ Volume không bất thường",
    ]
    extras = {
        "LONG":    ["☐ RSI chưa overbought (< 75)",
                    "☐ Nến xanh xác nhận trước khi vào"],
        "SHORT":   ["☐ RSI chưa oversold (> 25)",
                    "☐ Nến đỏ xác nhận trước khi vào"],
        "NEUTRAL": ["☐ Đặt Limit Order tại biên, KHÔNG Market Order",
                    "☐ Cancel lệnh còn lại khi 1 lệnh kích hoạt",
                    "☐ Breakout + volume cao → thoát ngay"],
    }
    return base + extras.get(direction, [])


def _build_invalidation(direction: str, primary, neutral_range) -> str:
    tf = primary.timeframe.upper()
    sr = primary.sr
    if direction == "LONG":
        return f"Nến {tf} đóng cửa dưới {_fmt(sr.nearest_support)} → Long vô hiệu"
    elif direction == "SHORT":
        return f"Nến {tf} đóng cửa trên {_fmt(sr.nearest_resistance)} → Short vô hiệu"
    elif neutral_range:
        return (f"Phá vỡ range [{_fmt(neutral_range.range_low)} – "
                f"{_fmt(neutral_range.range_high)}] với volume cao → Theo chiều breakout")
    return "Phá vỡ range với volume cao → Theo chiều breakout"