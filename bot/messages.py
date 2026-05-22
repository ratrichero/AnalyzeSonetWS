"""
Format tất cả messages gửi lên Telegram.
Hỗ trợ Markdown, số thập phân đầy đủ.
"""

from config import config


# ══════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════

def _fmt(v: float) -> str:
    """Format số – giữ đủ độ chính xác, không làm tròn sai."""
    if v == 0:        return "0"
    if v >= 10000:    return f"{v:,.2f}"
    if v >= 1000:     return f"{v:.3f}"
    if v >= 100:      return f"{v:.4f}"
    if v >= 1:        return f"{v:.5f}"
    if v >= 0.01:     return f"{v:.6f}"
    if v >= 0.0001:   return f"{v:.8f}"
    return f"{v:.10g}"


def _pct(a: float, b: float) -> str:
    """Tính % chênh lệch giữa 2 giá."""
    if b < 1e-12:
        return "0.00%"
    return f"{abs(a - b) / b * 100:.2f}%"


def _score_bar(score: float, width: int = 10) -> str:
    """Hiển thị score dạng progress bar."""
    pct    = (score + 1) / 2
    filled = round(pct * width)
    empty  = width - filled
    bar    = "█" * filled + "░" * empty
    emoji  = "🟢" if score > 0.2 else "🔴" if score < -0.2 else "⚪"
    return f"{emoji} [{bar}] {score:+.2f}"


def _direction_emoji(d: str) -> str:
    d = d.upper()
    if "LONG"  in d: return "🟢 LONG"
    if "SHORT" in d: return "🔴 SHORT"
    if "WAIT"  in d: return "⏳ WAIT"
    return "⚪ NEUTRAL"


def _signal_emoji(s: str) -> str:
    if s == "BULLISH": return "🟢"
    if s == "BEARISH": return "🔴"
    return "⚪"


# ══════════════════════════════════════════════════════════════════════
# WELCOME / HELP
# ══════════════════════════════════════════════════════════════════════

def welcome_message() -> str:
    return (
        "🤖 *Crypto Futures Analyzer Bot*\n\n"
        "Phân tích kỹ thuật Futures Binance.\n\n"
        "*Chức năng:*\n"
        "📊 *Phân tích Coin* – Chi tiết theo từng khung giờ\n"
        "🎯 *Khuyến nghị* – Tổng hợp đa khung + Entry/SL/TP\n\n"
        "Nhập tên coin VD: `BTC`, `ETH`, `SOL`\n"
        "hoặc chọn từ danh sách bên dưới."
    )


def help_message() -> str:
    return (
        "📖 *Hướng dẫn sử dụng*\n\n"
        "*1. Phân tích Coin*\n"
        "   • Gõ tên coin VD: `BTC`, `SOLUSDT`\n"
        "   • Chọn khung giờ: 15m / 1h / 4h / 1D\n"
        "   • Nhận báo cáo 5 nhóm chỉ báo\n\n"
        "*2. Khuyến nghị MTF*\n"
        "   • Phân tích đồng thời tất cả khung\n"
        "   • Hướng LONG / SHORT / NEUTRAL\n"
        "   • Entry, SL, TP1, TP2 cụ thể\n\n"
        "*Lưu ý Range Trading (NEUTRAL):*\n"
        "   • Luôn có 2 setup: Long tại Support, Short tại Resistance\n"
        "   • Đặt *Limit Order* tại Entry – KHÔNG Market Order\n"
        "   • Khi 1 lệnh khớp → Cancel lệnh còn lại\n\n"
        "⚠️ _Chỉ mang tính tham khảo – Tự chịu rủi ro_"
    )


# ══════════════════════════════════════════════════════════════════════
# SINGLE TIMEFRAME REPORT
# ══════════════════════════════════════════════════════════════════════

def format_single_report(report) -> str:
    r  = report
    tf = r.timeframe.upper()
    ts = r.trade_setup

    lines = [
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 *{r.symbol}* | Khung *{tf}*",
        f"💰 Giá hiện tại: `{_fmt(r.current_price)}`",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📋 *KẾT QUẢ PHÂN TÍCH 5 NHÓM*",
        "",
        # ── Nhóm 1: Xu hướng ──
        f"1️⃣ *Xu hướng (Trend)*",
        f"   {_signal_emoji(r.trend.signal)} {r.trend.signal}",
        f"   Score: {_score_bar(r.trend.score)}",
        f"   {r.trend.details['ema']['note']}",
        f"   {r.trend.details['macd']['note']}",
        f"   {r.trend.details['adx']['note']}",
        f"   {r.trend.details['ichimoku']['note']}",
        "",
        # ── Nhóm 2: Động lượng ──
        f"2️⃣ *Động lượng (Momentum)*",
        f"   {_signal_emoji(r.momentum.signal)} {r.momentum.signal}",
        f"   Score: {_score_bar(r.momentum.score)}",
        f"   {r.momentum.details['rsi']['note']}",
        f"   Stoch: {r.momentum.details['stochastic']['note']}",
        f"   {r.momentum.details['cci']['note']}",
        f"   {r.momentum.details['williams_r']['note']}",
        "",
        # ── Nhóm 3: Biến động ──
        f"3️⃣ *Biến động (Volatility)*",
        f"   Score: {_score_bar(r.volatility.score)}",
        f"   ATR: `{_fmt(r.volatility.atr_value)}` ({r.volatility.atr_pct:.3f}% giá)",
        f"   {r.volatility.details['bollinger']['note']}",
        f"   {r.volatility.details['squeeze']['note']}",
        "",
        # ── Nhóm 4: Khối lượng ──
        f"4️⃣ *Khối lượng (Volume)*",
        f"   {_signal_emoji(r.volume.signal)} {r.volume.signal}",
        f"   Score: {_score_bar(r.volume.score)}",
        f"   {r.volume.details['volume']['note']}",
        f"   OBV: {r.volume.details['obv']['note']}",
        f"   {r.volume.details['vwap']['note']}",
        f"   {r.volume.details['cmf']['note']}",
        "",
        # ── Nhóm 5: S/R ──
        f"5️⃣ *Hỗ trợ / Kháng cự*",
        f"   Score: {_score_bar(r.sr.score)}",
        f"   {r.sr.details['key_levels']['note']}",
        f"   {r.sr.details['fibonacci']['note']}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⭐ *TỔNG HỢP [{tf}]*",
        f"   Composite Score: {_score_bar(r.composite_score)}",
        f"   Tín hiệu: *{_direction_emoji(ts.direction)}*",
        "",
    ]

    # ── Setup theo hướng ───────────────────────────────────────
    if ts.direction == "NEUTRAL" and ts.long_setup and ts.short_setup:
        lines += _format_neutral_dual_setup(ts, r.current_price)
    elif ts.direction in ("LONG", "SHORT"):
        lines += _format_directional_setup(ts, r.current_price)
    else:
        lines += _format_wait_setup(ts)

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ _Chỉ mang tính tham khảo – Tự chịu rủi ro_",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# SETUP FORMATTERS
# ══════════════════════════════════════════════════════════════════════

def _format_neutral_dual_setup(ts, current_price: float) -> list:
    """
    Hiển thị 2 setup Long + Short cho NEUTRAL/Range Trading.
    Entry = tại biên S/R, không phải giá hiện tại.
    Hiển thị trạng thái: SẴN SÀNG VÀO / Chờ giá về.
    """
    ls = ts.long_setup
    ss = ts.short_setup

    dist_to_sup = (current_price - ts.range_low)  / current_price * 100
    dist_to_res = (ts.range_high - current_price) / current_price * 100
    range_pct   = (ts.range_high - ts.range_low)  / current_price * 100
    range_mid   = (ts.range_high + ts.range_low)  / 2
    pos_pct     = ts.price_position * 100

    # Progress bar
    bar_width = 18
    filled    = min(round(ts.price_position * bar_width), bar_width - 1)
    bar       = "▱" * filled + "◆" + "▱" * (bar_width - 1 - filled)

    # Trạng thái từng setup
    long_status  = (
        "🟢 *SẴN SÀNG VÀO*"
        if dist_to_sup <= 0.5
        else f"⏳ Chờ giá về (còn ↓{dist_to_sup:.2f}%)"
    )
    short_status = (
        "🔴 *SẴN SÀNG VÀO*"
        if dist_to_res <= 0.5
        else f"⏳ Chờ giá lên (còn ↑{dist_to_res:.2f}%)"
    )

    # Priority
    if ts.recommended == "LONG":
        priority = "✅ Ưu tiên *LONG* (tín hiệu thiên tăng)"
    elif ts.recommended == "SHORT":
        priority = "✅ Ưu tiên *SHORT* (tín hiệu thiên giảm)"
    else:
        priority = "⚖️ Cân bằng – 2 setup ngang nhau"

    lines = [
        "📍 *SETUP – RANGE TRADING*",
        "",
        f"   🔴 Resistance : `{_fmt(ts.range_high)}`  (+{dist_to_res:.2f}%)",
        f"   [{bar}]  {pos_pct:.0f}%",
        f"   💰 Giá htại  : `{_fmt(current_price)}`",
        f"   🟢 Support   : `{_fmt(ts.range_low)}`  (-{dist_to_sup:.2f}%)",
        f"   Range: `{range_pct:.2f}%` | Mid: `{_fmt(range_mid)}`",
        "",
        f"   {priority}",
        "",
        # ── LONG Setup ──
        "   ━━━━━━━━━━━━━━━━━━━━━━━",
        f"   🟢 *LONG*  |  {long_status}",
        f"   Đặt Limit Order TẠI Support:",
        f"   Entry : `{_fmt(ls.entry)}`",
        f"   SL    : `{_fmt(ls.sl)}`"
        f"  (↓ {_pct(ls.entry, ls.sl)} | -{_fmt(abs(ls.entry - ls.sl))})",
        f"   TP1   : `{_fmt(ls.tp1)}`"
        f"  (↑ {_pct(ls.tp1, ls.entry)}) – Midpoint",
        f"   TP2   : `{_fmt(ls.tp2)}`"
        f"  (↑ {_pct(ls.tp2, ls.entry)}) – Resistance",
        f"   R/R: `1:{ls.rr_ratio}`  |  Conf: `{ls.confidence:.0f}%`",
        f"   ⛔ {ls.invalidation}",
        "",
        # ── SHORT Setup ──
        "   ━━━━━━━━━━━━━━━━━━━━━━━",
        f"   🔴 *SHORT*  |  {short_status}",
        f"   Đặt Limit Order TẠI Resistance:",
        f"   Entry : `{_fmt(ss.entry)}`",
        f"   SL    : `{_fmt(ss.sl)}`"
        f"  (↑ {_pct(ss.sl, ss.entry)} | +{_fmt(abs(ss.sl - ss.entry))})",
        f"   TP1   : `{_fmt(ss.tp1)}`"
        f"  (↓ {_pct(ss.entry, ss.tp1)}) – Midpoint",
        f"   TP2   : `{_fmt(ss.tp2)}`"
        f"  (↓ {_pct(ss.entry, ss.tp2)}) – Support",
        f"   R/R: `1:{ss.rr_ratio}`  |  Conf: `{ss.confidence:.0f}%`",
        f"   ⛔ {ss.invalidation}",
        "",
        "   ━━━━━━━━━━━━━━━━━━━━━━━",
        "   💡 *Lưu ý:*",
        "   • Đặt 2 Limit Order tại Entry của 2 setup",
        "   • 1 lệnh khớp → Cancel lệnh còn lại ngay",
        "   • Breakout range + volume cao → thoát lệnh",
        "   • KHÔNG vào Market Order khi giá ở giữa range",
    ]
    return lines


def _format_directional_setup(ts, current_price: float) -> list:
    """Format setup LONG/SHORT rõ ràng."""
    is_long  = ts.direction == "LONG"
    emoji    = "🟢" if is_long else "🔴"
    sl_arrow = "↓" if is_long else "↑"
    tp_arrow = "↑" if is_long else "↓"

    # Khoảng cách entry từ giá hiện tại
    entry_diff     = current_price - ts.entry if is_long else ts.entry - current_price
    entry_diff_pct = entry_diff / current_price * 100
    entry_note     = (
        f"(↓ {entry_diff_pct:.2f}% từ giá htại – chờ pullback)"
        if is_long and entry_diff > 0
        else f"(↑ {entry_diff_pct:.2f}% từ giá htại – chờ pullback)"
        if not is_long and entry_diff > 0
        else "(tại giá hiện tại)"
    )

    lines = [
        f"📍 *SETUP GIAO DỊCH*",
        f"   {emoji} *{ts.direction}*",
        f"   Confidence: `{ts.confidence:.1f}%`",
        "",
    ]

    # Hiển thị context S/R nếu có
    if ts.range_high > 0 and ts.range_low > 0:
        if is_long:
            lines += [
                f"   🔴 Resistance: `{_fmt(ts.range_high)}`  "
                f"(+{_pct(ts.range_high, current_price)})",
                f"   💰 Giá htại:  `{_fmt(current_price)}`",
                f"   🟢 Support:   `{_fmt(ts.range_low)}`  "
                f"(-{_pct(current_price, ts.range_low)})",
                "",
            ]
        else:
            lines += [
                f"   🔴 Resistance: `{_fmt(ts.range_high)}`  "
                f"(+{_pct(ts.range_high, current_price)})",
                f"   💰 Giá htại:  `{_fmt(current_price)}`",
                f"   🟢 Support:   `{_fmt(ts.range_low)}`  "
                f"(-{_pct(current_price, ts.range_low)})",
                "",
            ]

    lines += [
        f"   Entry : `{_fmt(ts.entry)}`  {entry_note}",
        f"   SL    : `{_fmt(ts.sl)}`  "
        f"({sl_arrow} {_pct(ts.entry, ts.sl)})",
        f"   TP1   : `{_fmt(ts.tp1)}`  "
        f"({tp_arrow} {_pct(ts.tp1, ts.entry)})  R/R 1:1",
        f"   TP2   : `{_fmt(ts.tp2)}`  "
        f"({tp_arrow} {_pct(ts.tp2, ts.entry)})  R/R 1:{ts.rr_ratio}",
        "",
        "   💡 *Đặt Limit Order tại Entry*",
        "   Nếu giá không pullback về → bỏ qua, không FOMO",
        "",
        f"   ⛔ *Invalidation:* {ts.invalidation}",
    ]
    return lines


def _format_wait_setup(ts) -> list:
    """Khi không có setup tốt – chỉ hiển thị range."""
    lines = [
        "📍 *SETUP GIAO DỊCH*",
        "",
        "   ⏳ *WAIT – Chưa có setup tốt*",
        "   Giá đang ở giữa range, chờ về biên.",
        "",
    ]
    if ts.range_high > 0 and ts.range_low > 0:
        lines += [
            f"   🔴 Resistance: `{_fmt(ts.range_high)}`",
            f"   🟢 Support:    `{_fmt(ts.range_low)}`",
            "",
        ]
    lines += [
        "   💡 Chiến lược:",
        "   • Chờ giá về gần Support → xem xét LONG",
        "   • Chờ giá về gần Resistance → xem xét SHORT",
        "   • KHÔNG vào lệnh khi giá ở giữa range",
    ]
    return lines


# ══════════════════════════════════════════════════════════════════════
# MTF REPORT
# ══════════════════════════════════════════════════════════════════════

def format_mtf_report(mtf) -> str:
    ts = mtf.trade_setup

    lines = [
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 *KHUYẾN NGHỊ: {mtf.symbol}*",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📊 *PHÂN TÍCH ĐA KHUNG (MTF)*",
    ]

    for tf in config.TIMEFRAMES:
        if tf not in mtf.reports:
            continue
        r  = mtf.reports[tf]
        s  = r.composite_score
        em = "🟢" if s > 0.1 else "🔴" if s < -0.1 else "⚪"
        lines.append(
            f"   {em} *{tf.upper()}*: "
            f"Trend:{r.trend.signal[:4]} │ "
            f"Mom:{r.momentum.signal[:4]} │ "
            f"Vol:{r.volume.signal[:4]} → `{s:+.2f}`"
        )

    lines += [
        "",
        f"📈 *ĐIỂM ĐỒNG THUẬN*",
        f"   Score: {_score_bar(mtf.consensus_score, 12)}",
        f"   Đồng thuận: `{mtf.confidence:.0f}%`",
        f"   Khung mạnh nhất: `{mtf.best_timeframe.upper()}`",
        "",
        f"🎯 *HƯỚNG: {_direction_emoji(mtf.consensus_direction)}*",
        f"⚡ *RỦI RO: {mtf.risk_level}*",
        "",
        "📝 *LÝ DO*",
    ]
    for r in mtf.reasons:
        lines.append(f"   {r}")

    lines += [""]

    # ── Setup ─────────────────────────────────────────────────
    if mtf.consensus_direction == "NEUTRAL" and mtf.neutral_range:
        lines += _format_mtf_neutral_setup(mtf.neutral_range)
    elif mtf.consensus_direction in ("LONG", "SHORT"):
        primary_price = list(mtf.reports.values())[0].current_price
        lines += _format_directional_setup(ts, primary_price)
    else:
        lines += _format_wait_setup(ts)

    lines += [
        "",
        f"⛔ *INVALIDATION:* {mtf.invalidation}",
        "",
        "✅ *CHECKLIST*",
    ]
    for item in mtf.checklist:
        lines.append(f"   {item}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ _Chỉ mang tính tham khảo kỹ thuật._",
        "_Tối đa 1-2% tài khoản/lệnh._",
    ]
    return "\n".join(lines)


def _format_mtf_neutral_setup(nr) -> list:
    """Format NeutralRange cho MTF report."""
    current   = nr.current_price
    dist_sup  = (current - nr.range_low)  / current * 100
    dist_res  = (nr.range_high - current) / current * 100
    range_pct = (nr.range_high - nr.range_low) / current * 100

    bar_width = 18
    filled    = min(round(nr.price_position * bar_width), bar_width - 1)
    bar       = "▱" * filled + "◆" + "▱" * (bar_width - 1 - filled)

    long_status = (
        "🟢 *SẴN SÀNG*" if dist_sup <= 0.5
        else f"⏳ Còn ↓{dist_sup:.2f}%"
    )
    short_status = (
        "🔴 *SẴN SÀNG*" if dist_res <= 0.5
        else f"⏳ Còn ↑{dist_res:.2f}%"
    )

    if nr.recommended == "LONG":
        priority = "✅ Ưu tiên *LONG*"
    elif nr.recommended == "SHORT":
        priority = "✅ Ưu tiên *SHORT*"
    else:
        priority = "⚖️ Cân bằng 2 chiều"

    return [
        "📍 *SETUP – RANGE TRADING (MTF)*",
        "",
        f"   🔴 Resistance : `{_fmt(nr.range_high)}`  (+{dist_res:.2f}%)",
        f"   [{bar}]  {nr.price_position*100:.0f}%",
        f"   💰 Giá htại  : `{_fmt(current)}`",
        f"   🟢 Support   : `{_fmt(nr.range_low)}`  (-{dist_sup:.2f}%)",
        f"   Range: `{range_pct:.2f}%` | Mid: `{_fmt(nr.range_mid)}`",
        "",
        f"   {priority}",
        "",
        "   ━━━━━━━━━━━━━━━━━━━━━━━",
        f"   🟢 *LONG*  |  {long_status}",
        f"   Entry : `{_fmt(nr.long_entry)}`",
        f"   SL    : `{_fmt(nr.long_sl)}`"
        f"  (↓ {_pct(nr.long_entry, nr.long_sl)})",
        f"   TP1   : `{_fmt(nr.long_tp1)}`"
        f"  (↑ {_pct(nr.long_tp1, nr.long_entry)}) – Mid",
        f"   TP2   : `{_fmt(nr.long_tp2)}`"
        f"  (↑ {_pct(nr.long_tp2, nr.long_entry)}) – Resistance",
        f"   R/R: `1:{nr.long_rr}`",
        "",
        "   ━━━━━━━━━━━━━━━━━━━━━━━",
        f"   🔴 *SHORT*  |  {short_status}",
        f"   Entry : `{_fmt(nr.short_entry)}`",
        f"   SL    : `{_fmt(nr.short_sl)}`"
        f"  (↑ {_pct(nr.short_sl, nr.short_entry)})",
        f"   TP1   : `{_fmt(nr.short_tp1)}`"
        f"  (↓ {_pct(nr.short_entry, nr.short_tp1)}) – Mid",
        f"   TP2   : `{_fmt(nr.short_tp2)}`"
        f"  (↓ {_pct(nr.short_entry, nr.short_tp2)}) – Support",
        f"   R/R: `1:{nr.short_rr}`",
        "",
        "   ━━━━━━━━━━━━━━━━━━━━━━━",
        "   💡 Đặt 2 Limit Order tại 2 biên",
        "   1 lệnh khớp → Cancel lệnh còn lại ngay",
    ]