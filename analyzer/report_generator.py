"""
Tổng hợp kết quả 5 nhóm → báo cáo đầy đủ + khuyến nghị giao dịch.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from config import config


# ══════════════════════════════════════════════════════════════════════
# HELPER
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
    if go_up:
        return max(target, ref + min_diff)
    else:
        return min(target, ref - min_diff)


def _calc_rr(entry: float, sl: float, tp: float) -> float:
    risk   = abs(entry - sl)
    reward = abs(tp - entry)
    return round(reward / risk, 2) if risk > 0 else 0.0


# ══════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════
@dataclass
class SingleTradeSetup:
    """Setup cho 1 hướng giao dịch."""
    direction: str          # LONG | SHORT
    entry: float
    sl: float
    tp1: float
    tp2: float
    rr_ratio: float
    confidence: float
    invalidation: str

@dataclass 
class TradeSetup:
    """
    Setup giao dịch tổng hợp.
    - LONG/SHORT rõ ràng: chỉ có primary
    - NEUTRAL: có cả long_setup và short_setup
    """
    direction: str              # LONG | SHORT | NEUTRAL | WAIT
    # Setup chính (LONG/SHORT rõ ràng)
    entry: float = 0.0
    sl: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    rr_ratio: float = 0.0
    confidence: float = 0.0
    invalidation: str = ""
    # Range info
    range_low: float = 0.0
    range_high: float = 0.0
    price_position: float = -1.0
    # Neutral: 2 setup riêng
    long_setup: Optional[SingleTradeSetup] = None
    short_setup: Optional[SingleTradeSetup] = None
    recommended: str = ""       # "LONG" | "SHORT" | "BOTH" | "WAIT"

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
    """Vùng range trading hợp lệ - phải bao quanh giá hiện tại."""
    range_low: float
    range_high: float
    range_mid: float
    current_price: float
    price_position: float
    # Long setup
    long_entry: float
    long_sl: float
    long_tp1: float
    long_tp2: float
    long_rr: float
    # Short setup
    short_entry: float
    short_sl: float
    short_tp1: float
    short_tp2: float
    short_rr: float
    # Meta
    range_width_pct: float
    recommended: str        # "LONG" | "SHORT" | "WAIT"


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
    reasons: list = field(default_factory=list)
    checklist: list = field(default_factory=list)
    invalidation: str = ""
    neutral_range: Optional[NeutralRange] = None


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

    weights = {
        "trend":      0.30,
        "momentum":   0.25,
        "volatility": 0.15,
        "volume":     0.20,
        "sr":         0.10,
    }
    composite = (
        trend.score      * weights["trend"] +
        momentum.score   * weights["momentum"] +
        volatility.score * weights["volatility"] +
        volume.score     * weights["volume"] +
        sr.score         * weights["sr"]
    )
    composite = round(max(-1.0, min(1.0, composite)), 4)

    if composite > 0.25:    direction = "LONG"
    elif composite < -0.25: direction = "SHORT"
    else:                   direction = "NEUTRAL"

    if direction == "NEUTRAL":
        # Truyền composite để xét bias
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
    """
    Logic ưu tiên:
    1. Entry = pullback hợp lý
    2. TP2   = S/R đối diện (mục tiêu thực tế)
    3. SL    = tính từ R/R tối thiểu 1:2, sau đó so với S/R gần nhất
               → lấy mức nào chặt hơn (ít rủi ro hơn)
    4. TP1   = Entry ± risk × 1.0 (R/R 1:1)
    5. Validate toàn bộ thứ tự Entry/SL/TP
    """
    RR_MIN    = getattr(config, 'RR_MIN', 2.0)
    RR_TARGET = getattr(config, 'RR_TARGET', 2.5)
    RR_CAP    = getattr(config, 'RR_CAP', 8.0)
    min_diff  = atr14 * 0.03
    confidence = min(100.0, abs(composite) * 100 * 1.5)

    near_sup = sr.nearest_support
    near_res = sr.nearest_resistance

    valid_sup = near_sup > 0 and near_sup < close * 0.9995
    valid_res = near_res > 0 and near_res > close * 1.0005

    all_res = sorted([r for r in sr.key_levels.get("resistance", [])
                      if r > close * 1.001])
    all_sup = sorted([s for s in sr.key_levels.get("support", [])
                      if s < close * 0.999], reverse=True)

    # ══════════════════════════════════════════════════════
    # BƯỚC 1: XÁC ĐỊNH ENTRY (pullback hợp lý)
    # ══════════════════════════════════════════════════════
    if direction == "LONG":
        if valid_sup:
            dist_pct = (close - near_sup) / close
            if dist_pct <= 0.012:
                entry = near_sup * 1.002        # rất gần support
            elif dist_pct <= 0.025:
                entry = close - (close - near_sup) * 0.5   # retrace 50%
            elif dist_pct <= 0.05:
                entry = close - atr14 * 0.5     # pullback vừa
            else:
                entry = close - atr14 * 0.3     # pullback nhẹ
        else:
            entry = close - atr14 * 0.3

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

    # ══════════════════════════════════════════════════════
    # BƯỚC 2: XÁC ĐỊNH TP2 (mục tiêu xa dựa trên S/R)
    # ══════════════════════════════════════════════════════
    if direction == "LONG":
        if len(all_res) >= 2:
            tp2_sr = all_res[1] * 0.997
        elif len(all_res) == 1:
            tp2_sr = all_res[0] * 0.997
        else:
            tp2_sr = entry + atr14 * RR_TARGET * 1.5   # fallback ATR

    else:  # SHORT
        if len(all_sup) >= 2:
            tp2_sr = all_sup[1] * 1.003
        elif len(all_sup) == 1:
            tp2_sr = all_sup[0] * 1.003
        else:
            tp2_sr = entry - atr14 * RR_TARGET * 1.5

    # ══════════════════════════════════════════════════════
    # BƯỚC 3: TÍNH SL TỪ R/R TỐI THIỂU
    # ══════════════════════════════════════════════════════
    reward_full = abs(tp2_sr - entry)

    # SL từ R/R tối thiểu: risk = reward / RR_MIN
    risk_from_rr = reward_full / RR_MIN

    if direction == "LONG":
        sl_from_rr = entry - risk_from_rr

        # So sánh với S/R: lấy mức cao hơn (SL gần entry hơn = chặt hơn)
        if valid_sup:
            sl_from_sr = near_sup - atr14 * 0.2  # dưới support 1 chút
            sl = max(sl_from_rr, sl_from_sr)      # lấy mức cao hơn = ít risk hơn
        else:
            sl = sl_from_rr

        # Safety: SL không được cao hơn entry
        sl = min(sl, entry - min_diff)

    else:  # SHORT
        sl_from_rr = entry + risk_from_rr

        if valid_res:
            sl_from_sr = near_res + atr14 * 0.2   # trên resistance 1 chút
            sl = min(sl_from_rr, sl_from_sr)       # lấy mức thấp hơn = ít risk hơn
        else:
            sl = sl_from_rr

        # Safety: SL không được thấp hơn entry
        sl = max(sl, entry + min_diff)

    # ══════════════════════════════════════════════════════
    # BƯỚC 4: TP1 = Entry ± risk × 1.0 (breakeven+)
    # ══════════════════════════════════════════════════════
    actual_risk = abs(entry - sl)

    if direction == "LONG":
        tp1_base = entry + actual_risk * 1.0

        # TP1 không vượt resistance gần nhất
        if all_res:
            tp1 = min(tp1_base, all_res[0] * 0.997)
            tp1 = max(tp1, entry + min_diff)    # ít nhất > entry
        else:
            tp1 = tp1_base

        # TP2 phải > TP1
        tp2 = max(tp2_sr, tp1 + min_diff)

    else:  # SHORT
        tp1_base = entry - actual_risk * 1.0

        if all_sup:
            tp1 = max(tp1_base, all_sup[0] * 1.003)
            tp1 = min(tp1, entry - min_diff)
        else:
            tp1 = tp1_base

        tp2 = min(tp2_sr, tp1 - min_diff)

    # ══════════════════════════════════════════════════════
    # BƯỚC 5: VALIDATE & SANITY CHECK
    # ══════════════════════════════════════════════════════
    if direction == "LONG":
        # Đảm bảo thứ tự: SL < Entry < TP1 < TP2
        sl  = min(sl,  entry - min_diff)
        tp1 = max(tp1, entry + min_diff)
        tp2 = max(tp2, tp1   + min_diff)
    else:
        # Đảm bảo thứ tự: TP2 < TP1 < Entry < SL
        sl  = max(sl,  entry + min_diff)
        tp1 = min(tp1, entry - min_diff)
        tp2 = min(tp2, tp1   - min_diff)

    # Tính R/R thực tế
    actual_risk   = abs(entry - sl)
    actual_reward = abs(tp2   - entry)
    rr_actual     = actual_reward / actual_risk if actual_risk > 0 else 0.0

    # Nếu R/R vẫn > cap → điều chỉnh SL mở rộng
    if rr_actual > RR_CAP:
        ideal_risk = actual_reward / RR_CAP
        if direction == "LONG":
            sl = entry - ideal_risk
            sl = min(sl, entry - min_diff)
        else:
            sl = entry + ideal_risk
            sl = max(sl, entry + min_diff)
        rr_actual = _calc_rr(entry, sl, tp2)

    # Nếu R/R < 1.0 → TP quá gần → giảm confidence mạnh
    if rr_actual < 1.0:
        confidence = min(confidence, 20.0)
    elif rr_actual < RR_MIN:
        confidence = min(confidence, 35.0)

    # ══════════════════════════════════════════════════════
    # INVALIDATION
    # ══════════════════════════════════════════════════════
    if direction == "LONG":
        inv_level = near_sup if valid_sup else sl
        inv = f"Nến đóng cửa dưới Support {_fmt(inv_level)} → Long vô hiệu"
    else:
        inv_level = near_res if valid_res else sl
        inv = f"Nến đóng cửa trên Resistance {_fmt(inv_level)} → Short vô hiệu"

    return TradeSetup(
        direction=direction,
        entry=entry, sl=sl, tp1=tp1, tp2=tp2,
        rr_ratio=round(min(rr_actual, RR_CAP), 2),
        confidence=round(confidence, 1),
        invalidation=inv,
        range_low=near_sup  if valid_sup else 0.0,
        range_high=near_res if valid_res else 0.0,
        price_position=-1.0,
    )

def _get_valid_sr(close: float, atr14: float, sr) -> tuple:
    """
    Tìm Support và Resistance hợp lệ bao quanh giá hiện tại.
    Gộp tất cả levels từ key_levels, pivot, fibonacci.
    Trả về (near_sup, near_res, all_sup_below, all_res_above)
    """
    threshold = 0.0003  # tối thiểu cách giá 0.03%

    all_levels = []
    all_levels += sr.key_levels.get("resistance", [])
    all_levels += sr.key_levels.get("support", [])
    for v in sr.key_levels.get("pivots", {}).values():
        all_levels.append(v)
    for v in sr.key_levels.get("fibonacci", {}).values():
        all_levels.append(v)

    # Lọc hợp lệ
    sup_below = sorted(
        [v for v in all_levels if v < close * (1 - threshold) and v > 0],
        reverse=True    # cao nhất trước
    )
    res_above = sorted(
        [v for v in all_levels if v > close * (1 + threshold) and v > 0]
        # thấp nhất trước
    )

    # Fallback ATR
    near_sup = sup_below[0] if sup_below else close - atr14 * 2.0
    near_res = res_above[0] if res_above else close + atr14 * 2.0

    # Double-check
    if near_sup >= close: near_sup = close - atr14 * 2.0
    if near_res <= close: near_res = close + atr14 * 2.0

    return near_sup, near_res, sup_below, res_above

def _build_long_setup(
    near_sup: float,
    near_res: float,
    all_res_above: list,
    atr14: float,
    RR_MIN: float,
    RR_CAP: float,
    confidence: float,
) -> SingleTradeSetup:
    """
    Long setup tại biên dưới (support).
    Entry tại support, không phải giá hiện tại.
    SL dựa trên R/R tối thiểu.
    """
    min_diff = atr14 * 0.03

    # Entry: ngay trên support
    entry = near_sup * 1.003

    # TP2: resistance gần nhất hoặc xa hơn
    if len(all_res_above) >= 2:
        tp2_target = all_res_above[1] * 0.997
    elif len(all_res_above) == 1:
        tp2_target = all_res_above[0] * 0.997
    else:
        tp2_target = near_res * 0.997

    reward = abs(tp2_target - entry)

    # SL từ R/R tối thiểu
    risk_rr    = reward / RR_MIN
    sl_from_rr = entry - risk_rr
    # SL từ S/R: dưới support
    sl_from_sr = near_sup * 0.987
    # Lấy mức cao hơn (chặt hơn)
    sl = max(sl_from_rr, sl_from_sr)
    sl = min(sl, entry - min_diff)

    actual_risk = abs(entry - sl)

    # TP1: R/R 1:1
    tp1 = entry + actual_risk
    tp1 = min(tp1, near_res * 0.997)
    tp1 = max(tp1, entry + min_diff)

    tp2 = max(tp2_target, tp1 + min_diff)

    # Validate thứ tự SL < Entry < TP1 < TP2
    sl  = min(sl,  entry - min_diff)
    tp1 = max(tp1, entry + min_diff)
    tp2 = max(tp2, tp1   + min_diff)

    # Sanity R/R
    actual_risk   = abs(entry - sl)
    actual_reward = abs(tp2 - entry)
    rr = actual_reward / actual_risk if actual_risk > 1e-12 else 0.0

    if rr > RR_CAP:
        sl = entry - (actual_reward / RR_CAP)
        sl = min(sl, entry - min_diff)
        rr = _calc_rr(entry, sl, tp2)

    return SingleTradeSetup(
        direction="LONG",
        entry=entry, sl=sl, tp1=tp1, tp2=tp2,
        rr_ratio=round(min(rr, RR_CAP), 2),
        confidence=round(confidence, 1),
        invalidation=f"Nến đóng cửa dưới {_fmt(near_sup)} → Long vô hiệu",
    )


def _build_short_setup(
    near_sup: float,
    near_res: float,
    all_sup_below: list,
    atr14: float,
    RR_MIN: float,
    RR_CAP: float,
    confidence: float,
) -> SingleTradeSetup:
    """
    Short setup tại biên trên (resistance).
    Entry tại resistance, không phải giá hiện tại.
    SL dựa trên R/R tối thiểu.
    """
    min_diff = atr14 * 0.03

    # Entry: ngay dưới resistance
    entry = near_res * 0.997

    # TP2: support gần nhất hoặc xa hơn
    if len(all_sup_below) >= 2:
        tp2_target = all_sup_below[1] * 1.003
    elif len(all_sup_below) == 1:
        tp2_target = all_sup_below[0] * 1.003
    else:
        tp2_target = near_sup * 1.003

    reward = abs(entry - tp2_target)

    # SL từ R/R tối thiểu
    risk_rr    = reward / RR_MIN
    sl_from_rr = entry + risk_rr
    # SL từ S/R: trên resistance
    sl_from_sr = near_res * 1.013
    # Lấy mức thấp hơn (chặt hơn)
    sl = min(sl_from_rr, sl_from_sr)
    sl = max(sl, entry + min_diff)

    actual_risk = abs(sl - entry)

    # TP1: R/R 1:1
    tp1 = entry - actual_risk
    tp1 = max(tp1, near_sup * 1.003)
    tp1 = min(tp1, entry - min_diff)

    tp2 = min(tp2_target, tp1 - min_diff)

    # Validate thứ tự TP2 < TP1 < Entry < SL
    sl  = max(sl,  entry + min_diff)
    tp1 = min(tp1, entry - min_diff)
    tp2 = min(tp2, tp1   - min_diff)

    # Sanity R/R
    actual_risk   = abs(sl - entry)
    actual_reward = abs(entry - tp2)
    rr = actual_reward / actual_risk if actual_risk > 1e-12 else 0.0

    if rr > RR_CAP:
        sl = entry + (actual_reward / RR_CAP)
        sl = max(sl, entry + min_diff)
        rr = _calc_rr(entry, sl, tp2)

    return SingleTradeSetup(
        direction="SHORT",
        entry=entry, sl=sl, tp1=tp1, tp2=tp2,
        rr_ratio=round(min(rr, RR_CAP), 2),
        confidence=round(confidence, 1),
        invalidation=f"Nến đóng cửa trên {_fmt(near_res)} → Short vô hiệu",
    )

def _calc_neutral_single_setup(
    close: float,
    atr14: float,
    sr,
    composite: float,
) -> TradeSetup:
    """
    NEUTRAL → luôn đề xuất 2 setup: Long tại support + Short tại resistance.
    Dùng composite score để xác định setup nào được ưu tiên.
    """
    RR_MIN = getattr(config, 'RR_MIN', 2.0)
    RR_CAP = getattr(config, 'RR_CAP', 8.0)

    # Lấy S/R hợp lệ
    near_sup, near_res, all_sup_below, all_res_above = _get_valid_sr(
        close, atr14, sr
    )

    range_width = near_res - near_sup
    price_pos   = (
        (close - near_sup) / range_width
        if range_width > 1e-12 else 0.5
    )

    # ── Confidence cho từng hướng ──────────────────────────────
    # Dựa trên composite score + vị trí giá
    base_conf = 35.0

    if composite >= 0.08:
        # Thiên bullish → Long tự tin hơn
        long_conf  = base_conf + composite * 60      # tối đa ~50
        short_conf = base_conf - composite * 30      # thấp hơn
    elif composite <= -0.08:
        # Thiên bearish → Short tự tin hơn
        short_conf = base_conf + abs(composite) * 60
        long_conf  = base_conf - abs(composite) * 30
    else:
        # Thực sự flat
        long_conf  = base_conf
        short_conf = base_conf

    # Điều chỉnh theo vị trí giá trong range
    # Giá gần support → Long có lợi thế hơn
    long_conf  += (1 - price_pos) * 10
    short_conf += price_pos * 10

    # Cap tại 55% cho NEUTRAL
    long_conf  = round(min(long_conf,  55.0), 1)
    short_conf = round(min(short_conf, 55.0), 1)

    # ── Build 2 setup ──────────────────────────────────────────
    long_setup = _build_long_setup(
        near_sup, near_res, all_res_above,
        atr14, RR_MIN, RR_CAP, long_conf,
    )
    short_setup = _build_short_setup(
        near_sup, near_res, all_sup_below,
        atr14, RR_MIN, RR_CAP, short_conf,
    )

    # ── Xác định setup được ưu tiên ────────────────────────────
    if composite >= 0.08:
        recommended = "LONG"        # thiên bullish → ưu tiên Long
    elif composite <= -0.08:
        recommended = "SHORT"       # thiên bearish → ưu tiên Short
    else:
        recommended = "BOTH"        # thực sự neutral → cả 2 như nhau

    # ── TradeSetup tổng hợp ────────────────────────────────────
    # primary dùng để hiển thị tóm tắt (setup được ưu tiên)
    primary = long_setup if recommended in ("LONG", "BOTH") else short_setup

    return TradeSetup(
        direction="NEUTRAL",
        entry=primary.entry,
        sl=primary.sl,
        tp1=primary.tp1,
        tp2=primary.tp2,
        rr_ratio=primary.rr_ratio,
        confidence=primary.confidence,
        invalidation=primary.invalidation,
        range_low=near_sup,
        range_high=near_res,
        price_position=round(price_pos, 3),
        long_setup=long_setup,
        short_setup=short_setup,
        recommended=recommended,
    )

# ══════════════════════════════════════════════════════════════════════
# NEUTRAL RANGE – MULTI TIMEFRAME
# ══════════════════════════════════════════════════════════════════════

def _calc_neutral_range(reports: dict, current_price: float) -> Optional[NeutralRange]:
    """
    Tìm range hợp lệ bao quanh giá hiện tại từ các timeframe.
    Support phải THẤP HƠN giá, Resistance phải CAO HƠN giá.
    """
    all_supports    = []
    all_resistances = []

    for tf, rpt in reports.items():
        sr = rpt.sr

        for s in sr.key_levels.get("support", []):
            if s < current_price * 0.9995:
                all_supports.append(s)

        for r in sr.key_levels.get("resistance", []):
            if r > current_price * 1.0005:
                all_resistances.append(r)

        pivots = sr.key_levels.get("pivots", {})
        for k, v in pivots.items():
            if k.startswith("S") and v < current_price * 0.9995:
                all_supports.append(v)
            if k.startswith("R") and v > current_price * 1.0005:
                all_resistances.append(v)

        for k, v in sr.key_levels.get("fibonacci", {}).items():
            if v < current_price * 0.9995:
                all_supports.append(v)
            elif v > current_price * 1.0005:
                all_resistances.append(v)

    primary = reports.get("4h", list(reports.values())[0])
    atr_val = primary.volatility.atr_value

    if not all_supports or not all_resistances:
        return _fallback_range(current_price, atr_val)

    # Lấy support cao nhất bên dưới & resistance thấp nhất bên trên
    range_low  = max(all_supports)
    range_high = min(all_resistances)

    if range_low >= current_price or range_high <= current_price:
        return _fallback_range(current_price, atr_val)

    range_width_pct = (range_high - range_low) / current_price * 100
    if range_width_pct < 0.5:
        return _fallback_range(current_price, atr_val)

    return _build_neutral_range(range_low, range_high, current_price, atr_val)


def _fallback_range(price: float, atr: float) -> NeutralRange:
    range_low  = price - atr * 2.0
    range_high = price + atr * 2.0
    return _build_neutral_range(range_low, range_high, price, atr)


def _build_neutral_range(
    range_low: float,
    range_high: float,
    current_price: float,
    atr_val: float,
) -> NeutralRange:
    range_mid       = (range_low + range_high) / 2
    range_width_pct = (range_high - range_low) / current_price * 100
    price_position  = (current_price - range_low) / (range_high - range_low)
    min_diff        = atr_val * 0.05

    # Long setup
    long_entry = range_low  * 1.002
    long_sl    = range_low  * 0.988
    long_tp1   = range_mid
    long_tp2   = range_high * 0.996
    long_sl    = _ensure_diff(long_entry,  long_sl,  min_diff, go_up=False)
    long_tp1   = _ensure_diff(long_entry,  long_tp1, min_diff, go_up=True)
    long_tp2   = _ensure_diff(long_tp1,    long_tp2, min_diff, go_up=True)

    # Short setup
    short_entry = range_high * 0.998
    short_sl    = range_high * 1.012
    short_tp1   = range_mid
    short_tp2   = range_low  * 1.004
    short_sl    = _ensure_diff(short_entry, short_sl,  min_diff, go_up=True)
    short_tp1   = _ensure_diff(short_entry, short_tp1, min_diff, go_up=False)
    short_tp2   = _ensure_diff(short_tp1,   short_tp2, min_diff, go_up=False)

    if price_position <= 0.35:   recommended = "LONG"
    elif price_position >= 0.65: recommended = "SHORT"
    else:                        recommended = "WAIT"

    return NeutralRange(
        range_low=range_low, range_high=range_high,
        range_mid=range_mid, current_price=current_price,
        price_position=round(price_position, 3),
        long_entry=long_entry, long_sl=long_sl,
        long_tp1=long_tp1, long_tp2=long_tp2,
        long_rr=_calc_rr(long_entry, long_sl, long_tp2),
        short_entry=short_entry, short_sl=short_sl,
        short_tp1=short_tp1, short_tp2=short_tp2,
        short_rr=_calc_rr(short_entry, short_sl, short_tp2),
        range_width_pct=round(range_width_pct, 3),
        recommended=recommended,
    )


# ══════════════════════════════════════════════════════════════════════
# MULTI TIMEFRAME REPORT
# ══════════════════════════════════════════════════════════════════════

def generate_mtf_report(symbol: str, reports: dict) -> MTFReport:
    weights = config.TIMEFRAME_WEIGHTS
    score   = 0.0
    total_w = 0.0

    for tf, rpt in reports.items():
        w        = weights.get(tf, 0.25)
        score   += rpt.composite_score * w
        total_w += w

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
    current_price = primary.current_price

    neutral_range = None
    if direction == "NEUTRAL":
        neutral_range = _calc_neutral_range(reports, current_price)
        trade_setup   = _neutral_range_to_setup(neutral_range)
    else:
        trade_setup = primary.trade_setup

    return MTFReport(
        symbol=symbol,
        reports=reports,
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


def _neutral_range_to_setup(nr: NeutralRange) -> TradeSetup:
    if nr.recommended == "LONG":
        return TradeSetup(
            direction="LONG (Range)",
            entry=nr.long_entry, sl=nr.long_sl,
            tp1=nr.long_tp1, tp2=nr.long_tp2,
            rr_ratio=nr.long_rr, confidence=45.0,
            invalidation=f"Phá vỡ xuống dưới {_fmt(nr.long_sl)}",
            range_low=nr.range_low, range_high=nr.range_high,
            price_position=nr.price_position,
        )
    elif nr.recommended == "SHORT":
        return TradeSetup(
            direction="SHORT (Range)",
            entry=nr.short_entry, sl=nr.short_sl,
            tp1=nr.short_tp1, tp2=nr.short_tp2,
            rr_ratio=nr.short_rr, confidence=45.0,
            invalidation=f"Phá vỡ lên trên {_fmt(nr.short_sl)}",
            range_low=nr.range_low, range_high=nr.range_high,
            price_position=nr.price_position,
        )
    else:  # WAIT
        return TradeSetup(
            direction="WAIT",
            entry=nr.current_price,
            sl=nr.range_low * 0.988,
            tp1=nr.range_high * 0.996,
            tp2=nr.range_high * 0.996,
            rr_ratio=0.0, confidence=15.0,
            invalidation=f"Chờ giá về biên range",
            range_low=nr.range_low, range_high=nr.range_high,
            price_position=nr.price_position,
        )


# ══════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════

def _assess_risk(reports: dict, score: float) -> str:
    vol_scores = [r.volatility.atr_pct for r in reports.values()]
    avg_vol    = float(np.mean(vol_scores))
    abs_score  = abs(score)
    if avg_vol > 5 or abs_score < 0.15:    return "🔴 CAO"
    elif avg_vol > 2.5 or abs_score < 0.3: return "🟡 TRUNG BÌNH"
    else:                                   return "🟢 THẤP"


def _build_reasons(direction: str, reports: dict) -> list:
    header = {
        "LONG":    "📈 Lý do khuyến nghị LONG:",
        "SHORT":   "📉 Lý do khuyến nghị SHORT:",
        "NEUTRAL": "↔️ Thị trường sideway – Range Trading:",
    }
    reasons = [header.get(direction, "")]
    for tf in config.TIMEFRAMES:
        if tf not in reports:
            continue
        rpt = reports[tf]
        s   = rpt.composite_score
        em  = "🟢" if s > 0.1 else "🔴" if s < -0.1 else "⚪"
        reasons.append(
            f"  {em} [{tf.upper()}] Score={s:+.2f} │ "
            f"Trend:{rpt.trend.signal[:4]} │ "
            f"Mom:{rpt.momentum.signal[:4]} │ "
            f"Vol:{rpt.volume.signal[:4]}"
        )
    return reasons


def _build_checklist(direction: str) -> list:
    base = [
        "☐ Xác nhận tín hiệu entry trên nến 15m",
        "☐ Đặt SL ngay sau khi khớp lệnh",
        "☐ Kích thước vị thế ≤ 2% tài khoản/lệnh",
        "☐ Kiểm tra tin tức sắp ra",
        "☐ Volume không bất thường",
    ]
    extras = {
        "LONG":    ["☐ RSI chưa overbought (< 75)",
                    "☐ Nến xanh xác nhận trước khi vào"],
        "SHORT":   ["☐ RSI chưa oversold (> 25)",
                    "☐ Nến đỏ xác nhận trước khi vào"],
        "NEUTRAL": ["☐ Chờ giá chạm biên range, KHÔNG vào ở giữa",
                    "☐ Đặt limit order tại biên",
                    "☐ Cancel lệnh còn lại khi 1 lệnh kích hoạt",
                    "☐ Breakout khỏi range → theo chiều breakout"],
    }
    return base + extras.get(direction, [])


def _build_invalidation(direction: str, primary, neutral_range) -> str:
    sr = primary.sr
    tf = primary.timeframe.upper()
    if direction == "LONG":
        return (f"Nến {tf} đóng cửa dưới {_fmt(sr.nearest_support)} "
                f"→ Kế hoạch Long vô hiệu")
    elif direction == "SHORT":
        return (f"Nến {tf} đóng cửa trên {_fmt(sr.nearest_resistance)} "
                f"→ Kế hoạch Short vô hiệu")
    elif neutral_range:
        return (f"Giá phá vỡ range [{_fmt(neutral_range.range_low)} – "
                f"{_fmt(neutral_range.range_high)}] với volume cao "
                f"→ Theo chiều breakout")
    return "Giá phá vỡ range với volume cao → Theo chiều breakout"