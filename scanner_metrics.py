from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from KUCOIN.klines import Kline

EPS = 1e-12


@dataclass(frozen=True)
class CorridorLevels:
    low: float
    high: float
    mid: float
    pct: float


@dataclass(frozen=True)
class WickStats:
    """Primary wicks metric (v9 simplified).

    avg_wick_ratio: mean of (high-low)/abs(open-close) for qualifying candles.
    wick_count:     number of qualifying candles (pct_range gate passed, body > 0, range > 0).
    wick_share:     wick_count / total_candles.
    """
    avg_wick_ratio: float
    wick_count: int
    wick_share: float


@dataclass(frozen=True)
class DonchainStats:
    """Donchain range: (mean(highs[-N:]) / mean(lows[-N:]) - 1) * 100."""
    donchain_range: float


@dataclass(frozen=True)
class WallStats:
    top_level: float
    bottom_level: float
    top_cluster_spread_pct: float
    bottom_cluster_spread_pct: float
    top_touch_share: float
    bottom_touch_share: float
    recent_top_touch_share: float
    recent_bottom_touch_share: float
    best_side: str
    best_touch_share: float
    recent_best_touch_share: float
    best_cluster_spread_pct: float


@dataclass(frozen=True)
class AxisStats:
    axis: float
    axis_touch_share: float
    recent_axis_touch_count: int
    recent_axis_touch_share: float
    rotation_count: int
    return_to_axis_count: int
    avg_axis_distance_pct: float
    last_close_distance_to_axis_pct: float


@dataclass(frozen=True)
class RegimeStats:
    chop: float
    efficiency_ratio: float
    slope_to_corridor_ratio: float
    path_to_corridor_ratio: float
    avg_quote_turnover: float


def mean(xs: Iterable[float]) -> float:
    vals = [float(x) for x in xs]
    return float(sum(vals) / len(vals)) if vals else 0.0


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return float(a / b) if abs(b) > EPS else float(default)


def quantile(values: Sequence[float], q: float) -> float:
    arr = sorted(float(x) for x in values if math.isfinite(float(x)))
    if not arr:
        return 0.0
    if len(arr) == 1:
        return arr[0]
    q = min(max(float(q), 0.0), 1.0)
    idx = (len(arr) - 1) * q
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return arr[lo]
    frac = idx - lo
    return arr[lo] * (1.0 - frac) + arr[hi] * frac


def _upper_lower_wicks(k: Kline) -> Tuple[float, float]:
    upper = max(0.0, float(k.high) - max(float(k.open), float(k.close)))
    lower = max(0.0, min(float(k.open), float(k.close)) - float(k.low))
    return upper, lower


def _full_range(k: Kline) -> float:
    return max(0.0, float(k.high) - float(k.low))


def _true_range(cur: Kline, prev_close: float | None) -> float:
    high = float(cur.high)
    low = float(cur.low)
    if prev_close is None:
        return max(0.0, high - low)
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def direction_ratio(closes: Sequence[float]) -> float:
    if len(closes) < 2:
        return 1.0
    net_move = abs(closes[-1] - closes[0])
    path_sum = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    return safe_div(net_move, path_sum, default=1.0)


def linear_slope_to_range_ratio(closes: Sequence[float], corridor_width: float) -> float:
    n = len(closes)
    if n < 2 or corridor_width <= EPS:
        return 999.0
    xs = list(range(n))
    x_mean = (n - 1) / 2.0
    y_mean = mean(closes)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, closes))
    den = sum((x - x_mean) ** 2 for x in xs)
    slope = safe_div(num, den, default=0.0)
    total_line_move = abs(slope) * (n - 1)
    return safe_div(total_line_move, corridor_width, default=999.0)


def choppiness_index(klines: Sequence[Kline]) -> float:
    if len(klines) < 2:
        return 0.0
    trs: List[float] = []
    prev_close: float | None = None
    highs = []
    lows = []
    for k in klines:
        trs.append(_true_range(k, prev_close))
        prev_close = float(k.close)
        highs.append(float(k.high))
        lows.append(float(k.low))
    span = max(highs) - min(lows)
    if span <= EPS:
        return 100.0
    total_tr = sum(trs)
    n = len(klines)
    if total_tr <= EPS or n <= 1:
        return 0.0
    return max(0.0, min(100.0, 100.0 * math.log10(total_tr / span) / math.log10(n)))


def avg_quote_turnover(klines: Sequence[Kline]) -> float:
    vals = [k.turnover if k.turnover > 0 else (k.volume * k.close) for k in klines]
    return mean(vals)


def cluster_spread_pct(values: Sequence[float], k: int, reverse: bool) -> Tuple[float, float]:
    arr = sorted((float(x) for x in values if float(x) > 0), reverse=reverse)
    if not arr:
        return 999.0, 0.0
    take = max(1, min(int(k), len(arr)))
    picked = arr[:take]
    ref = statistics.median(picked)
    if ref <= 0:
        return 999.0, 0.0
    spread_pct = ((max(picked) - min(picked)) / ref) * 100.0
    return spread_pct, ref


def build_corridor(klines: Sequence[Kline], q_low: float, q_high: float) -> CorridorLevels:
    lows = [float(k.low) for k in klines if float(k.low) > 0]
    highs = [float(k.high) for k in klines if float(k.high) > 0]
    if not lows or not highs:
        return CorridorLevels(0.0, 0.0, 0.0, 0.0)
    low = quantile(lows, q_low)
    high = quantile(highs, q_high)
    if high <= low:
        low = min(lows)
        high = max(highs)
    mid = (high + low) / 2.0
    pct = safe_div(high - low, mid, default=0.0) * 100.0 if mid > 0 else 0.0
    return CorridorLevels(low=low, high=high, mid=mid, pct=pct)


def wick_stats(klines: Sequence[Kline], cfg) -> WickStats:
    """Simplified wicks (v9).

    A candle qualifies when:
      - (high - low) > 0  and  abs(open - close) > 0
      - (high / low - 1) * 100 >= cfg.min_pct_range

    For qualifying candles: ratio = (high - low) / abs(open - close).
    Returns avg ratio, count, and share of qualifying candles.
    """
    if not klines:
        return WickStats(0.0, 0, 0.0)

    min_pct_range = float(cfg.min_pct_range)
    ratios: List[float] = []

    for k in klines:
        full = float(k.high) - float(k.low)
        body = abs(float(k.open) - float(k.close))
        low_price = float(k.low)
        if body <= 0 or full <= 0 or low_price <= 0:
            continue
        pct_range = (float(k.high) / low_price - 1.0) * 100.0
        if pct_range < min_pct_range:
            continue
        ratios.append(full / body)

    n = len(klines)
    wick_count = len(ratios)
    return WickStats(
        avg_wick_ratio=mean(ratios) if ratios else 0.0,
        wick_count=wick_count,
        wick_share=wick_count / n if n > 0 else 0.0,
    )


def reclaim_share(klines: Sequence[Kline], lookback: int) -> float:
    """Secondary metric: fraction of candles that break a prior range and reclaim it.
    Used by the optional reclaim filter section.
    """
    if not klines:
        return 0.0
    lookback = max(1, int(lookback))
    count = 0
    for i in range(lookback, len(klines)):
        k = klines[i]
        prev = klines[max(0, i - lookback):i]
        prev_high = max(float(x.high) for x in prev)
        prev_low = min(float(x.low) for x in prev)
        close_inside = prev_low <= float(k.close) <= prev_high
        broke_up = float(k.high) > prev_high and close_inside and float(k.close) < float(k.high)
        broke_down = float(k.low) < prev_low and close_inside and float(k.close) > float(k.low)
        if broke_up or broke_down:
            count += 1
    return count / len(klines)


def donchain_stats(klines: Sequence[Kline], window: int) -> DonchainStats:
    """Donchain range over the last N candles.

    Formula: (mean(highs[-N:]) / mean(lows[-N:]) - 1) * 100
    """
    if not klines:
        return DonchainStats(0.0)
    n = max(1, min(int(window), len(klines)))
    recent = klines[-n:]
    highs = [float(k.high) for k in recent if float(k.high) > 0]
    lows = [float(k.low) for k in recent if float(k.low) > 0]
    if not highs or not lows:
        return DonchainStats(0.0)
    dc_range = safe_div(mean(highs) - mean(lows), mean(lows), default=0.0) * 100.0
    return DonchainStats(donchain_range=dc_range)


def wall_stats(klines: Sequence[Kline], cfg) -> WallStats:
    if not klines:
        return WallStats(0.0, 0.0, 999.0, 999.0, 0.0, 0.0, 0.0, 0.0, "none", 0.0, 0.0, 999.0)

    highs = [float(k.high) for k in klines if float(k.high) > 0]
    lows = [float(k.low) for k in klines if float(k.low) > 0]
    top_spread, top_level = cluster_spread_pct(highs, cfg.top_k_highs, reverse=True)
    bot_spread, bot_level = cluster_spread_pct(lows, cfg.bottom_k_lows, reverse=False)

    recent_window = max(1, min(len(klines), int(cfg.recent_window)))
    recent = klines[-recent_window:]
    top_tol = top_level * (cfg.touch_tolerance_pct / 100.0) if top_level > 0 else 0.0
    bot_tol = bot_level * (cfg.touch_tolerance_pct / 100.0) if bot_level > 0 else 0.0

    top_touches = sum(1 for k in klines if top_level > 0 and abs(float(k.high) - top_level) <= top_tol)
    bot_touches = sum(1 for k in klines if bot_level > 0 and abs(float(k.low) - bot_level) <= bot_tol)
    r_top = sum(1 for k in recent if top_level > 0 and abs(float(k.high) - top_level) <= top_tol)
    r_bot = sum(1 for k in recent if bot_level > 0 and abs(float(k.low) - bot_level) <= bot_tol)

    top_share = top_touches / len(klines)
    bot_share = bot_touches / len(klines)
    r_top_share = r_top / recent_window
    r_bot_share = r_bot / recent_window

    if r_top_share >= r_bot_share:
        best_side = "upper"
        best_touch = top_share
        recent_best = r_top_share
        best_spread = top_spread
    else:
        best_side = "lower"
        best_touch = bot_share
        recent_best = r_bot_share
        best_spread = bot_spread

    return WallStats(
        top_level=top_level,
        bottom_level=bot_level,
        top_cluster_spread_pct=top_spread,
        bottom_cluster_spread_pct=bot_spread,
        top_touch_share=top_share,
        bottom_touch_share=bot_share,
        recent_top_touch_share=r_top_share,
        recent_bottom_touch_share=r_bot_share,
        best_side=best_side,
        best_touch_share=best_touch,
        recent_best_touch_share=recent_best,
        best_cluster_spread_pct=best_spread,
    )


def _build_mode_axis(values: Sequence[float], low: float, high: float, bins: int) -> float:
    finite = [float(x) for x in values if math.isfinite(float(x))]
    if not finite:
        return 0.0
    if high <= low:
        return statistics.median(finite)
    bins = max(3, int(bins))
    step = max((high - low) / bins, EPS)
    counts = [0] * bins
    for v in finite:
        idx = int((min(max(v, low), high) - low) / step)
        idx = min(max(idx, 0), bins - 1)
        counts[idx] += 1
    best = max(range(bins), key=lambda i: counts[i])
    return low + (best + 0.5) * step


def axis_stats(klines: Sequence[Kline], corridor: CorridorLevels, cfg, activity_cfg) -> AxisStats:
    if not klines:
        return AxisStats(0.0, 0.0, 0, 0.0, 0, 0, 0.0, 0.0)

    closes = [float(k.close) for k in klines]
    hlc3 = [(float(k.high) + float(k.low) + float(k.close)) / 3.0 for k in klines]
    source = hlc3 if cfg.use_hlc3 else closes
    axis_mode = _build_mode_axis(source, corridor.low, corridor.high, cfg.mode_bins)
    median_close = statistics.median(closes) if closes else axis_mode
    median_hlc3 = statistics.median(hlc3) if hlc3 else axis_mode
    total_w = max(cfg.close_weight + cfg.hlc3_weight, EPS)
    blended = ((median_close * cfg.close_weight) + (median_hlc3 * cfg.hlc3_weight)) / total_w
    axis = (axis_mode * 0.65) + (blended * 0.35)

    tol_pct = float(cfg.tolerance_pct)
    recent_window = max(1, min(len(klines), int(cfg.recent_window)))
    touch_hits = 0
    distances: List[float] = []
    signs: List[int] = []

    for k in klines:
        close = float(k.close)
        h3 = (float(k.high) + float(k.low) + float(k.close)) / 3.0
        dist_close = abs(close - axis) / max(abs(axis), EPS) * 100.0
        dist_h3 = abs(h3 - axis) / max(abs(axis), EPS) * 100.0
        axis_inside_candle = float(k.low) <= axis <= float(k.high)
        dist = 0.0 if axis_inside_candle else min(dist_close, dist_h3)
        distances.append(dist)
        if dist <= tol_pct:
            touch_hits += 1
        signs.append(1 if close > axis else (-1 if close < axis else 0))

    # Rotation count: sign flips across axis, ignoring neutral touches.
    rotation_count = 0
    prev = 0
    for s in signs:
        if s == 0:
            continue
        if prev and s != prev:
            rotation_count += 1
        prev = s

    # Returns to axis band from one side back into tolerance.
    band_pct = max(0.0, float(activity_cfg.axis_band_pct))
    state = "inside"
    return_count = 0
    for close in closes:
        dist = abs(close - axis) / max(abs(axis), EPS) * 100.0
        cur = "inside" if dist <= band_pct else ("above" if close > axis else "below")
        if state in ("above", "below") and cur == "inside":
            return_count += 1
        state = cur

    recent_distances = distances[-recent_window:]
    recent_touches = sum(1 for d in recent_distances if d <= tol_pct)
    return AxisStats(
        axis=axis,
        axis_touch_share=touch_hits / len(klines),
        recent_axis_touch_count=recent_touches,
        recent_axis_touch_share=recent_touches / recent_window,
        rotation_count=rotation_count,
        return_to_axis_count=return_count,
        avg_axis_distance_pct=mean(distances),
        last_close_distance_to_axis_pct=distances[-1] if distances else 0.0,
    )


def regime_stats(klines: Sequence[Kline], corridor: CorridorLevels) -> RegimeStats:
    closes = [float(k.close) for k in klines]
    hlc3 = [(float(k.high) + float(k.low) + float(k.close)) / 3.0 for k in klines]
    corridor_width = max(corridor.high - corridor.low, EPS)
    path_source = hlc3 if len(hlc3) > 1 else closes
    path = sum(abs(path_source[i] - path_source[i - 1]) for i in range(1, len(path_source))) if len(path_source) > 1 else 0.0
    return RegimeStats(
        chop=choppiness_index(klines),
        efficiency_ratio=direction_ratio(closes),
        slope_to_corridor_ratio=linear_slope_to_range_ratio(closes, corridor_width),
        path_to_corridor_ratio=safe_div(path, corridor_width, default=0.0),
        avg_quote_turnover=avg_quote_turnover(klines),
    )
