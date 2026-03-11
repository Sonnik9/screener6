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
    avg_wick_ratio: float
    long_wick_share: float
    two_sided_wick_share: float
    false_break_reclaim_share: float


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



def ema(values: Sequence[float], period: int) -> List[float]:
    if not values:
        return []
    p = max(1, int(period))
    alpha = 2.0 / (p + 1.0)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(alpha * float(v) + (1.0 - alpha) * out[-1])
    return out



def _body_floor(k: Kline, body_floor_range_share: float, body_floor_pct: float) -> float:
    full_range = max(EPS, abs(float(k.high) - float(k.low)))
    return max(
        full_range * max(body_floor_range_share, 0.0),
        abs(float(k.close)) * max(body_floor_pct, 0.0) / 100.0,
        EPS,
    )



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
    if not klines:
        return WickStats(0.0, 0.0, 0.0, 0.0)

    long_hits = 0
    two_sided_hits = 0
    false_reclaims = 0
    wick_ratios: List[float] = []

    for i, k in enumerate(klines):
        full = max(_full_range(k), EPS)
        upper, lower = _upper_lower_wicks(k)
        body_eff = max(abs(float(k.open) - float(k.close)), _body_floor(k, cfg.body_floor_range_share, cfg.body_floor_pct))
        dominant = max(upper, lower)
        dominant_share = dominant / full
        dominant_ratio = dominant / body_eff
        wick_ratios.append((upper + lower) / body_eff)

        if dominant_ratio >= cfg.long_wick_ratio and dominant_share >= cfg.min_dominant_wick_share:
            long_hits += 1

        upper_share = upper / full
        lower_share = lower / full
        if upper_share >= cfg.min_two_sided_share_per_candle and lower_share >= cfg.min_two_sided_share_per_candle:
            small = min(upper, lower)
            big = max(upper, lower)
            imbalance = safe_div(big, max(small, EPS), default=999.0)
            if imbalance <= cfg.max_two_sided_imbalance:
                two_sided_hits += 1

        if i >= max(1, int(getattr(cfg, "reclaim_lookback", 6) or 6)):
            prev = klines[max(0, i - int(getattr(cfg, "reclaim_lookback", 6) or 6)):i]
            prev_high = max(x.high for x in prev)
            prev_low = min(x.low for x in prev)
            close_inside_prev = prev_low <= k.close <= prev_high
            broke_up = k.high > prev_high and close_inside_prev and k.close < k.high
            broke_down = k.low < prev_low and close_inside_prev and k.close > k.low
            if broke_up or broke_down:
                false_reclaims += 1

    n = len(klines)
    return WickStats(
        avg_wick_ratio=mean(wick_ratios),
        long_wick_share=long_hits / n,
        two_sided_wick_share=two_sided_hits / n,
        false_break_reclaim_share=false_reclaims / n,
    )



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

    # Rotation count = sign flips across the axis, ignoring neutral touches.
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
