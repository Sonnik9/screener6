from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FilterSummary:
    candles_count: int
    corridor_low: float
    corridor_high: float
    corridor_mid: float
    corridor_pct: float
    structural_axis: float
    axis_touch_count: int
    axis_touch_share: float
    recent_axis_touch_count: int
    recent_axis_touch_share: float
    rotation_count: int
    return_to_axis_count: int
    avg_axis_distance_pct: float
    # Primary wicks metrics (v9 simplified)
    avg_wick_ratio: float
    wick_count: int
    wick_share: float
    # Secondary: reclaim section
    false_break_reclaim_share: float
    # Primary: donchain
    donchain_range: float
    chop: float
    efficiency_ratio: float
    slope_to_corridor_ratio: float
    path_to_corridor_ratio: float
    top_wall_touch_share: float
    bottom_wall_touch_share: float
    recent_top_wall_touch_share: float
    recent_bottom_wall_touch_share: float
    wall_side: str
    wall_touch_share: float
    recent_wall_touch_share: float
    top_wall_cluster_spread_pct: float
    bottom_wall_cluster_spread_pct: float
    wall_cluster_spread_pct: float
    avg_quote_turnover: float
    last_close_distance_to_axis_pct: float
    score: float
    score_pct: float
