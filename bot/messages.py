"""
Format tất cả messages gửi lên Telegram.
Hỗ trợ MarkdownV2, tự động escape.
Số thập phân hiển thị đầy đủ, không làm tròn sai.
"""

from analyzer.report_generator import FullReport, MTFReport, TradeSetup
from config import config


# ══════════════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════════════

def _fmt(v: float, decimals: int = None) -> str:
    """Format số – tự chọn độ chính xác phù hợp."""
    if v == 0:
        return "0"
    if decimals is not None:
        return f"{v:.{decimals}f}"
    if v >= 10000:   return f"{v:,.2f}"
    if v >= 1000:    return f"{v:.3f}"
    if v >= 100:     return f"{v:.4f}"
    if v >= 1:       return f"{v:.5f}"
    if v >= 0.01:    return f"{v:.6f}"
    if v >= 0.0001:  return f"{v:.8f}"
    return f"{v:.10g}"


def _score_bar(score: float, width: int = 10) -> str:
    """Hiển thị score dạng progress bar."""
    pct     = (score + 1) / 2       # -1..1 → 0..1
    filled  = round(pct * width)
    empty   = width - filled
    bar     = "█" * filled + "░" * empty
    arrow   = "🟢" if score > 0.2 else "🔴" if score < -0.2 else "⚪"
    return f"{arrow} [{bar}] {score:+.2f}"


def _direction_emoji(d: str) -> str:
    d = d.upper()
    if "LONG"  in d: return "🟢 LONG"
    if "SHORT" in d: return "🔴 SHORT"
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
        "Chào mừng! Bot phân tích kỹ thuật Futures Binance.\n\n"
        "*Chức năng:*\n"
        "📊 *Phân tích Coin* – Chi tiết theo từng khung giờ\n"
        "🎯 *Khuyến nghị* – Tổng hợp đa khung + Entry/SL/TP\n\n"
        "Nhập tên coin (VD: `BTCUSDT`, `ETH`) hoặc chọn từ menu."
    )


def help_message() -> str:
    return (
        "📖 *Hướng dẫn sử dụng*\n\n"
        "*1. Phân tích Coin*\n"
        "   • Gõ tên coin VD: `BTC` hoặc `BTCUSDT`\n"
        "   • Hoặc nhấn *Coin phổ biến* để chọn\n"
        "   • Chọn khung giờ: 15m / 1h / 4h / 1D\n\n"
        "*2. Khuyến nghị*\n"
        "   • Phân tích đồng thời tất cả khung\n"
        "   • Đưa ra hướng LONG / SHORT / NEUTRAL\n"
        "   • Kèm Entry, SL, TP1, TP2 cụ thể\n\n"
        "*Chú ý:*\n"
        "⚠️ Bot chỉ phân tích kỹ thuật, KHÔNG phải tư vấn đầu tư.\n"
        "💡 Luôn quản lý rủi ro và chỉ dùng vốn có thể chấp nhận mất."
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
        f"1️⃣ *Xu hướng (Trend)*",
        f"   {_signal_emoji(r.trend.signal)} {r.trend.signal}",
        f"   Score: {_score_bar(r.trend.score)}",
        f"   {r.trend.details['ema']['note']}",
        f"   {r.trend.details['macd']['note']}",
        f"   {r.trend.details['adx']['note']}",
        f"   {r.trend.details['ichimoku']['note']}",
        "",
        f"2️⃣ *Động lượng (Momentum)*",
        f"   {_signal_emoji(r.momentum.signal)} {r.momentum.signal}",
        f"   Score: {_score_bar(r.momentum.score)}",
        f"   {r.momentum.details['rsi']['note']}",
        f"   Stoch: {r.momentum.details['stochastic']['note']}",
        f"   {r.momentum.details['cci']['note']}",
        f"   {r.momentum.details['williams_r']['note']}",
        "",
        f"3️⃣ *Biến động (Volatility)*",
        f"   Score: {_score_bar(r.volatility.score)}",
        f"   ATR: {_fmt(r.volatility.atr_value)} ({r.volatility.atr_pct:.3f}% giá)",
        f"   {r.volatility.details['bollinger']['note']}",
        f"   {r.volatility.details['squeeze']['note']}",
        "",
        f"4️⃣ *Khối lượng (Volume)*",
        f"   {_signal_emoji(r.volume.signal)} {r.volume.signal}",
        f"   Score: {_score_bar(r.volume.score)}",
        f"   {r.volume.details['volume']['note']}",
        f"   OBV: {r.volume.details['obv']['note']}",
        f"   {r.volume.details['vwap']['note']}",
        f"   {r.volume.details['cmf']['note']}",
        "",
        f"5️⃣ *Hỗ trợ / Kháng cự*",
        f"   Score: {_score_bar(r.sr.score)}",
        f"   {r.sr.details['key_levels']['note']}",
        f"   {r.sr.details['fibonacci']['note']}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⭐ *TỔNG HỢP [{tf}]*",
        f"   Composite Score: {_score_bar(r.composite_score)}",
        f"   Tín hiệu thị trường: *{_direction_emoji(ts.direction)}*",
        "",
    ]

    # ── Setup theo hướng ───────────────────────────────────────
    if ts.direction == "NEUTRAL" and ts.long_setup and ts.short_setup:
        lines += _format_neutral_dual_setup(ts, r.current_price)
    elif ts.direction in ("LONG", "SHORT"):
        lines += _format_directional_setup(ts)
    else:
        lines += _format_wait_setup(ts)

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ _Chỉ mang tính tham khảo – Tự chịu rủi ro_",
    ]
    return "\n".join(lines)


def _format_neutral_dual_setup(ts, current_price: float) -> list:
    """Hiển thị 2 setup Long + Short khi NEUTRAL."""
    ls = ts.long_setup
    ss = ts.short_setup

    # Progress bar vị trí giá
    pos       = ts.price_position if ts.price_position >= 0 else 0.5
    bar_width = 18
    filled    = min(round(pos * bar_width), bar_width - 1)
    bar       = "▱" * filled + "◆" + "▱" * (bar_width - 1 - filled)

    # Label ưu tiên
    if ts.recommended == "LONG":
        priority_label = "✅ *Ưu tiên LONG* (tín hiệu thiên tăng)"
    elif ts.recommended == "SHORT":
        priority_label = "✅ *Ưu tiên SHORT* (tín hiệu thiên giảm)"
    else:
        priority_label = "⚖️ *Cân bằng* – cả 2 setup có giá trị ngang nhau"

    # Tính % từng mức
    def pct(a, b):
        return abs(a - b) / b * 100 if b > 1e-12 else 0.0

    lines = [
        "📍 *SETUP GIAO DỊCH – RANGE TRADING*",
        "",
        f"   🔴 Resistance: `{_fmt(ts.range_high)}`",
        f"   [{bar}]  {pos*100:.0f}% trong range",
        f"   💰 Giá hiện tại: `{_fmt(current_price)}`",
        f"   🟢 Support:    `{_fmt(ts.range_low)}`",
        f"   Độ rộng range: `{(ts.range_high - ts.range_low) / current_price * 100:.2f}%`",
        "",
        f"   {priority_label}",
        "",
        # ── LONG Setup ──
        "   ─────────────────────────",
        f"   🟢 *LONG – Vào tại biên dưới (Support)*",
        f"   Confidence: `{ls.confidence:.1f}%`",
        f"   Entry : `{_fmt(ls.entry)}`  "
        f"(↓ {pct(current_price, ls.entry):.2f}% từ giá hiện tại)",
        f"   SL    : `{_fmt(ls.sl)}`    "
        f"(↓ {pct(ls.entry, ls.sl):.2f}%)",
        f"   TP1   : `{_fmt(ls.tp1)}`  "
        f"(↑ {pct(ls.tp1, ls.entry):.2f}%)  R/R 1:1",
        f"   TP2   : `{_fmt(ls.tp2)}`  "
        f"(↑ {pct(ls.tp2, ls.entry):.2f}%)  R/R 1:{ls.rr_ratio}",
        f"   ⛔ {ls.invalidation}",
        "",
        # ── SHORT Setup ──
        "   ─────────────────────────",
        f"   🔴 *SHORT – Vào tại biên trên (Resistance)*",
        f"   Confidence: `{ss.confidence:.1f}%`",
        f"   Entry : `{_fmt(ss.entry)}`  "
        f"(↑ {pct(ss.entry, current_price):.2f}% từ giá hiện tại)",
        f"   SL    : `{_fmt(ss.sl)}`    "
        f"(↑ {pct(ss.sl, ss.entry):.2f}%)",
        f"   TP1   : `{_fmt(ss.tp1)}`  "
        f"(↓ {pct(ss.entry, ss.tp1):.2f}%)  R/R 1:1",
        f"   TP2   : `{_fmt(ss.tp2)}`  "
        f"(↓ {pct(ss.entry, ss.tp2):.2f}%)  R/R 1:{ss.rr_ratio}",
        f"   ⛔ {ss.invalidation}",
        "",
        "   ─────────────────────────",
        "   💡 *Lưu ý Range Trading:*",
        "   • Đặt Limit Order tại Entry, không Market Order",
        "   • Khi 1 lệnh kích hoạt → Cancel lệnh còn lại",
        "   • Breakout khỏi range với volume cao → thoát ngay",
    ]
    return lines


def _format_directional_setup(ts) -> list:
    """Format setup LONG/SHORT rõ ràng."""
    is_long = ts.direction == "LONG"
    emoji   = "🟢" if is_long else "🔴"
    sl_dir  = "↓" if is_long else "↑"
    tp_dir  = "↑" if is_long else "↓"

    def pct(a, b):
        return abs(a - b) / b * 100 if b > 1e-12 else 0.0

    lines = [
        f"📍 *SETUP GIAO DỊCH*",
        f"   {emoji} *{ts.direction}*",
        f"   Confidence: `{ts.confidence:.1f}%`",
        "",
    ]

    if ts.range_high > 0 and ts.range_low > 0:
        lines += [
            f"   Resistance: `{_fmt(ts.range_high)}`",
            f"   Support:    `{_fmt(ts.range_low)}`",
            "",
        ]

    lines += [
        f"   Entry : `{_fmt(ts.entry)}`",
        f"   SL    : `{_fmt(ts.sl)}`   "
        f"({sl_dir} {pct(ts.entry, ts.sl):.2f}%)",
        f"   TP1   : `{_fmt(ts.tp1)}`  "
        f"({tp_dir} {pct(ts.tp1, ts.entry):.2f}%)  R/R 1:1",
        f"   TP2   : `{_fmt(ts.tp2)}`  "
        f"({tp_dir} {pct(ts.tp2, ts.entry):.2f}%)  R/R 1:{ts.rr_ratio}",
        "",
        f"   💡 Đặt Limit Order tại Entry, chờ giá pullback.",
        f"   Không FOMO nếu giá không về Entry.",
        "",
        f"   ⛔ *Invalidation:* {ts.invalidation}",
    ]
    return lines


def _format_wait_setup(ts) -> list:
    """Khi không có setup tốt."""
    return [
        "📍 *SETUP GIAO DỊCH*",
        "",
        "   ⏳ *WAIT – Chưa có setup tốt*",
        "",
        f"   Range hiện tại:",
        f"   🔴 Resistance: `{_fmt(ts.range_high)}`"
        if ts.range_high > 0 else "",
        f"   🟢 Support:    `{_fmt(ts.range_low)}`"
        if ts.range_low > 0 else "",
        "",
        "   💡 Chờ giá về biên range rồi mới vào lệnh.",
        "   Không giao dịch khi giá ở giữa vùng không rõ ràng.",
    ]

# ══════════════════════════════════════════════════════════════════════
# MTF REPORT (KHUYẾN NGHỊ)
# ══════════════════════════════════════════════════════════════════════

def format_mtf_report(mtf) -> str:
    """Format MTF report hoàn chỉnh."""
    ts  = mtf.trade_setup
    dir_text = _direction_emoji(mtf.consensus_direction)

    lines = [
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 *KHUYẾN NGHỊ: {mtf.symbol}*",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"",
        "📊 *PHÂN TÍCH ĐA KHUNG (MTF)*",
    ]

    for tf in config.TIMEFRAMES:
        if tf not in mtf.reports:
            continue
        r  = mtf.reports[tf]
        em = "🟢" if r.composite_score > 0.1 else "🔴" if r.composite_score < -0.1 else "⚪"
        lines.append(
            f"   {em} *{tf.upper()}*: {r.trend.signal[:4]}|"
            f"{r.momentum.signal[:4]}|{r.volume.signal[:4]}"
            f" → `{r.composite_score:+.2f}`"
        )

    lines += [
        f"",
        f"📈 *ĐIỂM ĐỒNG THUẬN*",
        f"   Score tổng hợp: {_score_bar(mtf.consensus_score, 12)}",
        f"   Tỷ lệ đồng thuận: `{mtf.confidence:.0f}%`",
        f"   Khung mạnh nhất: `{mtf.best_timeframe.upper()}`",
        f"",
        f"🎯 *HƯỚNG KHUYẾN NGHỊ: {dir_text}*",
        f"",
        "📝 *LÝ DO*",
    ]
    for r in mtf.reasons:
        lines.append(f"   {r}")

    lines += [
        f"",
        f"⚡ *MỨC ĐỘ RỦI RO: {mtf.risk_level}*",
        f"",
    ]

    # Setup
    if mtf.consensus_direction == "NEUTRAL" and mtf.neutral_range:
        lines += _format_neutral_setup(mtf.neutral_range)
    else:
        lines += _format_directional_setup(ts)

    lines += [
        f"",
        f"⛔ *ĐIỀU KIỆN VÔ HIỆU HÓA*",
        f"   {mtf.invalidation}",
        f"",
        "✅ *CHECKLIST*",
    ]
    for item in mtf.checklist:
        lines.append(f"   {item}")

    lines += [
        f"",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ _Chỉ mang tính tham khảo kỹ thuật._",
        "_Luôn quản lý rủi ro – tối đa 1-2% tài khoản/lệnh._",
    ]
    return "\n".join(lines)


def _format_directional_setup(ts: TradeSetup) -> list:
    """Format setup LONG/SHORT với Entry logic."""
    is_long  = ts.direction == "LONG"
    close    = ts.entry  # entry đã được tính, không phải giá hiện tại nữa
    sl_pct   = abs(ts.entry - ts.sl)    / ts.entry * 100
    tp1_pct  = abs(ts.tp1   - ts.entry) / ts.entry * 100
    tp2_pct  = abs(ts.tp2   - ts.entry) / ts.entry * 100
    sl_dir   = "↓" if is_long else "↑"
    tp_dir   = "↑" if is_long else "↓"
    emoji    = "🟢" if is_long else "🔴"

    lines = [
        f"📍 *SETUP GIAO DỊCH*",
        f"   {emoji} *{ts.direction}*",
        f"",
    ]

    # Hiển thị range context nếu có
    if ts.range_high > 0 and ts.range_low > 0:
        if is_long:
            lines += [
                f"   Resistance:  `{_fmt(ts.range_high)}`  ← TP zone",
                f"   Entry:       `{_fmt(ts.entry)}`  ← Vùng pullback",
                f"   Support:     `{_fmt(ts.range_low)}`  ← SL zone",
                f"",
            ]
        else:
            lines += [
                f"   Resistance:  `{_fmt(ts.range_high)}`  ← SL zone",
                f"   Entry:       `{_fmt(ts.entry)}`  ← Vùng pullback",
                f"   Support:     `{_fmt(ts.range_low)}`  ← TP zone",
                f"",
            ]

    lines += [
        f"   Entry:  `{_fmt(ts.entry)}`",
        f"   SL:     `{_fmt(ts.sl)}`  ({sl_dir} {sl_pct:.2f}%)",
        f"   TP1:    `{_fmt(ts.tp1)}`  ({tp_dir} {tp1_pct:.2f}%)",
        f"   TP2:    `{_fmt(ts.tp2)}`  ({tp_dir} {tp2_pct:.2f}%)",
        f"   R/R:    `1:{ts.rr_ratio}`",
        f"   Confidence: `{ts.confidence:.1f}%`",
    ]

    # Thêm note về entry
    lines += [
        f"",
        f"   💡 *Entry không phải giá hiện tại:*",
        f"   Đặt Limit Order tại Entry, chờ giá pullback.",
        f"   Nếu giá không retrace → bỏ qua, không FOMO.",
    ]

    return lines


def _format_neutral_setup(nr) -> list:
    """Format NeutralRange object – hiển thị đầy đủ thông tin."""

    # Indicator vị trí giá
    pos_pct = nr.price_position * 100
    if pos_pct <= 35:
        pos_label = f"🔽 Gần biên DƯỚI ({pos_pct:.0f}%)"
    elif pos_pct >= 65:
        pos_label = f"🔼 Gần biên TRÊN ({pos_pct:.0f}%)"
    else:
        pos_label = f"➡️ Giữa range ({pos_pct:.0f}%)"

    # Progress bar vị trí giá trong range
    bar_width = 20
    filled    = round(nr.price_position * bar_width)
    bar       = "─" * filled + "●" + "─" * (bar_width - filled)

    lines = [
        "📍 *SETUP RANGE TRADING*",
        f"",
        f"   Biên trên (Resistance): `{_fmt(nr.range_high)}`",
        f"   [{bar}]",
        f"   Giá hiện tại:           `{_fmt(nr.current_price)}`  {pos_label}",
        f"   [{' ' * bar_width}]",
        f"   Biên dưới (Support):    `{_fmt(nr.range_low)}`",
        f"   Độ rộng range: `{nr.range_width_pct:.2f}%`",
        f"",
    ]

    # Khuyến nghị ưu tiên
    if nr.recommended == "LONG":
        lines.append("   ✅ *Ưu tiên: LONG* (giá gần biên dưới)")
    elif nr.recommended == "SHORT":
        lines.append("   ✅ *Ưu tiên: SHORT* (giá gần biên trên)")
    else:
        lines.append("   ⏳ *Khuyến nghị: WAIT* (giá ở giữa range)")
        lines.append("   💡 Chờ giá về biên range rồi mới vào lệnh")

    lines += [
        f"",
        f"   🟢 *LONG – Vào tại biên dưới:*",
        f"      Entry: `{_fmt(nr.long_entry)}`  (ngay trên Support)",
        f"      SL:    `{_fmt(nr.long_sl)}`   (dưới Support)",
        f"      TP1:   `{_fmt(nr.long_tp1)}`  (giữa range)",
        f"      TP2:   `{_fmt(nr.long_tp2)}`  (gần Resistance)",
        f"      R/R:   `1:{nr.long_rr}`",
        f"",
        f"   🔴 *SHORT – Vào tại biên trên:*",
        f"      Entry: `{_fmt(nr.short_entry)}`  (ngay dưới Resistance)",
        f"      SL:    `{_fmt(nr.short_sl)}`   (trên Resistance)",
        f"      TP1:   `{_fmt(nr.short_tp1)}`  (giữa range)",
        f"      TP2:   `{_fmt(nr.short_tp2)}`  (gần Support)",
        f"      R/R:   `1:{nr.short_rr}`",
    ]
    return lines