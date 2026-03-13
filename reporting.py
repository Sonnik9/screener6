from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict


def _f(metrics: Dict[str, Any], key: str, default: Any = 0.0) -> Any:
    return metrics.get(key, default)


def _min_check(actual: Any, min_value: Any) -> Dict[str, Any]:
    return {
        "actual": actual,
        "min": min_value,
        "passed": float(actual) >= float(min_value),
    }


def _max_check(actual: Any, max_value: Any) -> Dict[str, Any]:
    return {
        "actual": actual,
        "max": max_value,
        "passed": float(actual) <= float(max_value),
    }


def build_filter_metrics_view(timeframe: str, lookback_candles: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "timeframe": timeframe,
        "lookback_candles": int(lookback_candles),
        "min_score_pct": _f(metrics, "score_pct"),
        "regime": {
            "corridor_low": _f(metrics, "corridor_low"),
            "corridor_high": _f(metrics, "corridor_high"),
            "corridor_mid": _f(metrics, "corridor_mid"),
            "min_corridor_pct": _f(metrics, "corridor_pct"),
            "max_corridor_pct": _f(metrics, "corridor_pct"),
            "min_chop": _f(metrics, "chop"),
            "max_efficiency_ratio": _f(metrics, "efficiency_ratio"),
            "max_slope_to_corridor_ratio": _f(metrics, "slope_to_corridor_ratio"),
        },
        # PRIMARY wicks (v9 simplified)
        "wicks": {
            "avg_wick_ratio": _f(metrics, "avg_wick_ratio"),
            "wick_count": _f(metrics, "wick_count", 0),
            "wick_share": _f(metrics, "wick_share"),
        },
        # PRIMARY donchain
        "donchain": {
            "donchain_range": _f(metrics, "donchain_range"),
        },
        "axis": {
            "structural_axis": _f(metrics, "structural_axis"),
            "axis_touch_count": _f(metrics, "axis_touch_count"),
            "min_axis_touch_share": _f(metrics, "axis_touch_share"),
            "min_recent_axis_touches": _f(metrics, "recent_axis_touch_count"),
            "recent_axis_touch_share": _f(metrics, "recent_axis_touch_share"),
            "min_rotation_count": _f(metrics, "rotation_count"),
            "avg_axis_distance_pct": _f(metrics, "avg_axis_distance_pct"),
            "last_close_distance_to_axis_pct": _f(metrics, "last_close_distance_to_axis_pct"),
        },
        "wall": {
            "wall_side": _f(metrics, "wall_side", "none"),
            "min_recent_wall_touch_share": _f(metrics, "recent_wall_touch_share"),
            "min_full_wall_touch_share": _f(metrics, "wall_touch_share"),
            "max_cluster_spread_pct": _f(metrics, "wall_cluster_spread_pct"),
            "recent_top_wall_touch_share": _f(metrics, "recent_top_wall_touch_share"),
            "recent_bottom_wall_touch_share": _f(metrics, "recent_bottom_wall_touch_share"),
            "top_wall_touch_share": _f(metrics, "top_wall_touch_share"),
            "bottom_wall_touch_share": _f(metrics, "bottom_wall_touch_share"),
            "top_wall_cluster_spread_pct": _f(metrics, "top_wall_cluster_spread_pct"),
            "bottom_wall_cluster_spread_pct": _f(metrics, "bottom_wall_cluster_spread_pct"),
        },
        "activity": {
            "min_path_to_corridor_ratio": _f(metrics, "path_to_corridor_ratio"),
            "min_return_to_axis_count": _f(metrics, "return_to_axis_count"),
            "avg_quote_turnover": _f(metrics, "avg_quote_turnover"),
        },
        "reclaim": {
            "min_false_break_reclaim_share": _f(metrics, "false_break_reclaim_share"),
        },
        "liquidity": {
            "min_avg_quote_turnover": _f(metrics, "avg_quote_turnover"),
        },
    }


def build_filter_config_view(filter_cfg: Any) -> Dict[str, Any]:
    if is_dataclass(filter_cfg):
        return asdict(filter_cfg)
    if hasattr(filter_cfg, "__dict__"):
        return {k: build_filter_config_view(v) if hasattr(v, "__dict__") or is_dataclass(v) else v for k, v in vars(filter_cfg).items()}
    if isinstance(filter_cfg, dict):
        return {k: build_filter_config_view(v) if isinstance(v, dict) else v for k, v in filter_cfg.items()}
    return {"value": filter_cfg}


def build_filter_checks(filter_cfg: Any, metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "score": {
            "enabled": True,
            "score_pct": _min_check(_f(metrics, "score_pct"), filter_cfg.min_score_pct),
        },
        "regime": {
            "enabled": bool(filter_cfg.regime.enabled),
            "corridor_min": _min_check(_f(metrics, "corridor_pct"), filter_cfg.regime.min_corridor_pct),
            "corridor_max": _max_check(_f(metrics, "corridor_pct"), filter_cfg.regime.max_corridor_pct),
            "chop": _min_check(_f(metrics, "chop"), filter_cfg.regime.min_chop),
            "efficiency_ratio": _max_check(_f(metrics, "efficiency_ratio"), filter_cfg.regime.max_efficiency_ratio),
            "slope_to_corridor_ratio": _max_check(_f(metrics, "slope_to_corridor_ratio"), filter_cfg.regime.max_slope_to_corridor_ratio),
        },
        # PRIMARY wicks (v9)
        "wicks": {
            "enabled": bool(filter_cfg.wicks.enabled),
            "avg_wick_ratio": _min_check(_f(metrics, "avg_wick_ratio"), filter_cfg.wicks.min_avg_wick_ratio),
            "wick_count": _min_check(_f(metrics, "wick_count", 0), filter_cfg.wicks.min_wick_count),
        },
        # PRIMARY donchain
        "donchain": {
            "enabled": bool(filter_cfg.donchain.enabled),
            "donchain_range_min": _min_check(_f(metrics, "donchain_range"), filter_cfg.donchain.min_donchain_range),
            "donchain_range_max": _max_check(_f(metrics, "donchain_range"), filter_cfg.donchain.max_donchain_range),
        },
        "axis": {
            "enabled": bool(filter_cfg.axis.enabled),
            "axis_touch_share": _min_check(_f(metrics, "axis_touch_share"), filter_cfg.axis.min_axis_touch_share),
            "recent_axis_touch_count": _min_check(_f(metrics, "recent_axis_touch_count"), filter_cfg.axis.min_recent_axis_touches),
            "rotation_count": _min_check(_f(metrics, "rotation_count"), filter_cfg.axis.min_rotation_count),
        },
        "wall": {
            "enabled": bool(filter_cfg.wall.enabled),
            "recent_wall_touch_share": _min_check(_f(metrics, "recent_wall_touch_share"), filter_cfg.wall.min_recent_wall_touch_share),
            "wall_touch_share": _min_check(_f(metrics, "wall_touch_share"), filter_cfg.wall.min_full_wall_touch_share),
            "wall_cluster_spread_pct": _max_check(_f(metrics, "wall_cluster_spread_pct"), filter_cfg.wall.max_cluster_spread_pct),
        },
        "activity": {
            "enabled": bool(filter_cfg.activity.enabled),
            "path_to_corridor_ratio": _min_check(_f(metrics, "path_to_corridor_ratio"), filter_cfg.activity.min_path_to_corridor_ratio),
            "return_to_axis_count": _min_check(_f(metrics, "return_to_axis_count"), filter_cfg.activity.min_return_to_axis_count),
        },
        "reclaim": {
            "enabled": bool(filter_cfg.reclaim.enabled),
            "false_break_reclaim_share": _min_check(_f(metrics, "false_break_reclaim_share"), filter_cfg.reclaim.min_false_break_reclaim_share),
        },
        "liquidity": {
            "enabled": bool(filter_cfg.liquidity.enabled),
            "avg_quote_turnover": _min_check(_f(metrics, "avg_quote_turnover"), filter_cfg.liquidity.min_avg_quote_turnover),
        },
    }
