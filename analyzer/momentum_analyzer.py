"""Nhóm 2 – Động lượng (Momentum)"""

import pandas as pd
from dataclasses import dataclass, field
from analyzer.indicators import rsi, stochastic, cci, williams_r, macd


@dataclass
class MomentumResult:
    score: float
    signal: str
    details: dict = field(default_factory=dict)
    summary: str = ""


def analyze_momentum(df: pd.DataFrame) -> MomentumResult:
    score   = 0.0
    details = {}

    # ── RSI ────────────────────────────────────────────────────────
    rsi_val  = rsi(df, 14)
    rsi_last = float(rsi_val.iloc[-1])
    rsi_prev = float(rsi_val.iloc[-2])

    rsi_score = 0.0
    if rsi_last > 70:        rsi_score = -0.8   # overbought
    elif rsi_last > 60:      rsi_score =  0.5   # bullish momentum
    elif rsi_last > 50:      rsi_score =  0.2
    elif rsi_last > 40:      rsi_score = -0.2
    elif rsi_last > 30:      rsi_score = -0.5   # bearish momentum
    else:                    rsi_score =  0.8   # oversold (tiềm năng đảo chiều)

    # Divergence cơ bản (RSI tăng/giảm so với nến trước)
    if rsi_last > rsi_prev:  rsi_score += 0.1
    else:                    rsi_score -= 0.1
    rsi_score = max(-1.0, min(1.0, rsi_score))

    details["rsi"] = {
        "value": round(rsi_last, 2),
        "score": round(rsi_score, 3),
        "zone":  ("Overbought" if rsi_last > 70 else
                  "Oversold"   if rsi_last < 30 else "Normal"),
        "note":  f"RSI={rsi_last:.1f} – {'tăng' if rsi_last > rsi_prev else 'giảm'}",
    }
    score += rsi_score * 0.35

    # ── Stochastic ─────────────────────────────────────────────────
    k, d       = stochastic(df, 14, 3)
    k_last     = float(k.iloc[-1])
    d_last     = float(d.iloc[-1])

    stoch_score = 0.0
    if k_last > 80:                         stoch_score = -0.6   # overbought
    elif k_last < 20:                       stoch_score =  0.6   # oversold
    elif k_last > d_last and k_last > 50:   stoch_score =  0.4
    elif k_last < d_last and k_last < 50:   stoch_score = -0.4
    stoch_score = max(-1.0, min(1.0, stoch_score))

    details["stochastic"] = {
        "k": round(k_last, 2), "d": round(d_last, 2),
        "score": round(stoch_score, 3),
        "note":  (f"%K={k_last:.1f} {'>' if k_last > d_last else '<'} %D={d_last:.1f}, "
                  f"{'Overbought' if k_last > 80 else 'Oversold' if k_last < 20 else 'Normal'}"),
    }
    score += stoch_score * 0.25

    # ── CCI ────────────────────────────────────────────────────────
    cci_val  = cci(df, 20)
    cci_last = float(cci_val.iloc[-1])

    cci_score = 0.0
    if cci_last > 100:    cci_score = -0.5
    elif cci_last < -100: cci_score =  0.5
    else:                 cci_score = cci_last / 200   # linear scale

    details["cci"] = {
        "value": round(cci_last, 2),
        "score": round(cci_score, 3),
        "note":  (f"CCI={cci_last:.1f} – "
                  f"{'Overbought' if cci_last > 100 else 'Oversold' if cci_last < -100 else 'Bình thường'}"),
    }
    score += cci_score * 0.20

    # ── Williams %R ────────────────────────────────────────────────
    wr_val  = williams_r(df, 14)
    wr_last = float(wr_val.iloc[-1])

    wr_score = 0.0
    if wr_last > -20:    wr_score = -0.7   # overbought
    elif wr_last < -80:  wr_score =  0.7   # oversold
    else:                wr_score = (wr_last + 50) / 50 * (-0.5)

    details["williams_r"] = {
        "value": round(wr_last, 2),
        "score": round(wr_score, 3),
        "note":  f"W%R={wr_last:.1f}",
    }
    score += wr_score * 0.20

    # ── Tổng hợp ───────────────────────────────────────────────────
    score = max(-1.0, min(1.0, score))
    if score > 0.2:    signal = "BULLISH"
    elif score < -0.2: signal = "BEARISH"
    else:              signal = "NEUTRAL"

    summary = _build_summary(signal, score, details)
    return MomentumResult(score=round(score, 4), signal=signal,
                          details=details, summary=summary)


def _build_summary(signal: str, score: float, details: dict) -> str:
    lines = [f"⚡ *Động lượng:* {signal} (Score: {score:+.2f})"]
    lines.append(f"  • {details['rsi']['note']}")
    lines.append(f"  • Stoch: {details['stochastic']['note']}")
    lines.append(f"  • CCI: {details['cci']['note']}")
    lines.append(f"  • Williams: {details['williams_r']['note']}")
    return "\n".join(lines)