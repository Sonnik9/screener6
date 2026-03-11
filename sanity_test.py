from __future__ import annotations

import math
from dataclasses import asdict

from config import load_config, CFG_PATH
from scanner_engine import CandidateScanner
from KUCOIN.klines import Kline


def build_sideways_pattern(n: int = 120, axis: float = 100.0) -> list[Kline]:
    out: list[Kline] = []
    for i in range(n):
        phase = i / 6.0
        close = axis + math.sin(phase) * 1.2 + math.sin(phase * 0.65) * 0.55
        open_ = axis + math.sin((i - 1) / 6.0) * 1.1
        wiggle = 0.10 + abs(math.sin(i * 1.7)) * 0.08
        upper = 0.75 + abs(math.sin(i * 0.9)) * 1.00
        lower = 0.70 + abs(math.cos(i * 1.1)) * 0.90
        # recent upper wall pressure
        if i > n - 18:
            close = axis + 1.25 + math.sin(i * 0.4) * 0.18
            upper += 0.50
            lower += 0.20
        high = max(open_, close) + upper
        low = min(open_, close) - lower
        out.append(Kline(ts_ms=i * 60_000, open=open_, high=high, low=low, close=close, volume=1000.0, turnover=100000.0))
    return out


def build_trend_pattern(n: int = 120, start: float = 100.0) -> list[Kline]:
    out: list[Kline] = []
    for i in range(n):
        open_ = start + i * 0.25
        close = open_ + 0.20
        high = close + 0.18
        low = open_ - 0.12
        out.append(Kline(ts_ms=i * 60_000, open=open_, high=high, low=low, close=close, volume=1000.0, turnover=100000.0))
    return out


def build_dead_flat(n: int = 120, axis: float = 100.0) -> list[Kline]:
    out: list[Kline] = []
    for i in range(n):
        open_ = axis + math.sin(i * 0.1) * 0.03
        close = axis + math.sin(i * 0.11) * 0.03
        high = max(open_, close) + 0.05
        low = min(open_, close) - 0.05
        out.append(Kline(ts_ms=i * 60_000, open=open_, high=high, low=low, close=close, volume=1000.0, turnover=100000.0))
    return out


if __name__ == "__main__":
    cfg = load_config(CFG_PATH)
    scanner = CandidateScanner(cfg)
    calc = scanner.calc

    good = calc.summarize(build_sideways_pattern())
    trend = calc.summarize(build_trend_pattern())
    flat = calc.summarize(build_dead_flat())

    print("GOOD:", good.score_pct, good.corridor_pct, good.chop, good.recent_wall_touch_share, good.rotation_count)
    print("TREND:", trend.score_pct, trend.corridor_pct, trend.chop, trend.recent_wall_touch_share, trend.rotation_count)
    print("FLAT:", flat.score_pct, flat.corridor_pct, flat.chop, flat.recent_wall_touch_share, flat.rotation_count)

    # quick smoke pass/fail using production filters
    for label, summary in [("GOOD", good), ("TREND", trend), ("FLAT", flat)]:
        m = scanner._build_metrics(label, build_sideways_pattern() if label == "GOOD" else build_trend_pattern() if label == "TREND" else build_dead_flat())
        passed, reasons = scanner._passes_filters(m)
        print(label, passed, reasons)


    # approximation mode check: should relax only score threshold, not bypass other active filters
    cfg.filter.approximation.enabled = True
    cfg.filter.approximation.min_match_pct = 80.0
    m_good = scanner._build_metrics("GOOD", build_sideways_pattern())
    m_trend = scanner._build_metrics("TREND", build_trend_pattern())
    print("APPROX GOOD", scanner._passes_filters(m_good))
    print("APPROX TREND", scanner._passes_filters(m_trend))


print("CFG reverse enabled:", cfg.reverse.enabled, "slot:", cfg.reverse.slot)
