from __future__ import annotations

import argparse
import asyncio
import json
import math
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from c_log import UnifiedLogger
from config import CFG_PATH, ConfigLoader, load_config
from filters import CalculatingEngine
from KUCOIN.klines import Kline, KucoinKlines
from reporting import build_filter_checks, build_filter_metrics_view

ROOT = Path(__file__).resolve().parent
OUT_PATH = ROOT / "reverse_report.json"
UTC = timezone.utc
logger = UnifiedLogger("reverse")


class CandidateTf:
    @staticmethod
    def to_minutes(tf: str) -> int:
        mapping = {
            "1m": 1,
            "3m": 3,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
            "2h": 120,
            "4h": 240,
            "8h": 480,
            "1d": 1440,
        }
        key = str(tf).lower().strip()
        if key not in mapping:
            raise ValueError(f"Unsupported timeframe: {tf}")
        return mapping[key]


def _dt_utc(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _quantile(values: Sequence[float], q: float) -> float:
    arr = sorted(float(x) for x in values if x is not None and math.isfinite(float(x)))
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


def _round(v: Any, digits: int = 6) -> float:
    try:
        return round(float(v), digits)
    except Exception:
        return 0.0


def _round_cfg_float(v: Any) -> float:
    try:
        fv = float(v)
    except Exception:
        return 0.0
    av = abs(fv)
    if av >= 10:
        return round(fv, 1)
    if av >= 1:
        return round(fv, 2)
    if av >= 0.1:
        return round(fv, 3)
    return round(fv, 4)


def _floor_int(v: Any) -> int:
    try:
        return max(0, int(math.floor(float(v))))
    except Exception:
        return 0


def _ceil_int(v: Any) -> int:
    try:
        return max(0, int(math.ceil(float(v))))
    except Exception:
        return 0


def _clamp(v: float, min_v: float | None = None, max_v: float | None = None) -> float:
    out = float(v)
    if min_v is not None:
        out = max(float(min_v), out)
    if max_v is not None:
        out = min(float(max_v), out)
    return out


def _normalize_symbol(symbol: str) -> str:
    s = str(symbol).upper().strip()
    if s.endswith("M"):
        return s
    if s.endswith("USDT") or s.endswith("USDC"):
        return f"{s}M"
    return s


def _window_endpoints(start_dt: datetime, end_dt: datetime, step_minutes: int) -> List[datetime]:
    out: List[datetime] = []
    cur = start_dt
    step = timedelta(minutes=max(1, int(step_minutes)))
    while cur <= end_dt:
        out.append(cur)
        cur += step
    return out


def _slice_last(candles: Sequence[Kline], end_ms: int, limit: int) -> List[Kline]:
    eligible = [k for k in candles if int(k.ts_ms) <= int(end_ms)]
    if limit > 0:
        eligible = eligible[-int(limit):]
    return eligible


def _collect_metric(rows: Sequence[Dict[str, Any]], key: str) -> List[float]:
    out: List[float] = []
    for row in rows:
        metrics = row.get("metrics") or {}
        if key in metrics:
            try:
                out.append(float(metrics[key]))
            except Exception:
                continue
    return out


def _summary_stats(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    keys = [
        "score_pct",
        "corridor_pct",
        "chop",
        "efficiency_ratio",
        "slope_to_corridor_ratio",
        # PRIMARY wicks (v9)
        "avg_wick_ratio",
        "wick_count",
        "wick_share",
        # PRIMARY donchain
        "donchain_range",
        "axis_touch_share",
        "recent_axis_touch_count",
        "rotation_count",
        "recent_wall_touch_share",
        "wall_touch_share",
        "wall_cluster_spread_pct",
        "path_to_corridor_ratio",
        "return_to_axis_count",
        "false_break_reclaim_share",
    ]
    out: Dict[str, Any] = {}
    for key in keys:
        vals = _collect_metric(rows, key)
        if not vals:
            continue
        out[key] = {
            "min": _round(min(vals), 6),
            "q10": _round(_quantile(vals, 0.10), 6),
            "median": _round(median(vals), 6),
            "q90": _round(_quantile(vals, 0.90), 6),
            "max": _round(max(vals), 6),
        }
    return out


def _s(summary: Dict[str, Any], key: str, field: str, default: float = 0.0) -> float:
    try:
        return float(((summary.get(key) or {}).get(field, default)))
    except Exception:
        return float(default)


def _slot_wrapper(filter_slot: Dict[str, Any]) -> Dict[str, Any]:
    return {"filter": filter_slot}


def _copy_json(obj: Any) -> Any:
    return json.loads(json.dumps(obj))


def _build_base_filter(summary: Dict[str, Any], cfg_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    filt = _copy_json((cfg_snapshot or {}).get("filter") or {})
    if not summary:
        return filt

    score_q10 = _s(summary, "score_pct", "q10")
    corridor_q10 = _s(summary, "corridor_pct", "q10")
    corridor_q90 = _s(summary, "corridor_pct", "q90")
    chop_q10 = _s(summary, "chop", "q10")
    eff_q90 = _s(summary, "efficiency_ratio", "q90")
    eff_median = _s(summary, "efficiency_ratio", "median")
    slope_q90 = _s(summary, "slope_to_corridor_ratio", "q90")
    slope_median = _s(summary, "slope_to_corridor_ratio", "median")
    # PRIMARY wicks (v9)
    avg_wick_q10 = _s(summary, "avg_wick_ratio", "q10")
    wick_count_q10 = _s(summary, "wick_count", "q10")
    # PRIMARY donchain
    donchain_q10 = _s(summary, "donchain_range", "q10")
    donchain_q90 = _s(summary, "donchain_range", "q90")
    axis_touch_q10 = _s(summary, "axis_touch_share", "q10")
    recent_axis_q10 = _s(summary, "recent_axis_touch_count", "q10")
    rotation_q10 = _s(summary, "rotation_count", "q10")
    recent_wall_q10 = _s(summary, "recent_wall_touch_share", "q10")
    recent_wall_q90 = _s(summary, "recent_wall_touch_share", "q90")
    recent_wall_median = _s(summary, "recent_wall_touch_share", "median")
    wall_touch_q10 = _s(summary, "wall_touch_share", "q10")
    wall_cluster_q90 = _s(summary, "wall_cluster_spread_pct", "q90")
    wall_cluster_median = _s(summary, "wall_cluster_spread_pct", "median")
    path_q10 = _s(summary, "path_to_corridor_ratio", "q10")
    returns_q10 = _s(summary, "return_to_axis_count", "q10")
    reclaim_q10 = _s(summary, "false_break_reclaim_share", "q10")

    filt["min_score_pct"] = _round_cfg_float(score_q10 * 0.99)

    regime = filt.setdefault("regime", {})
    regime["min_corridor_pct"] = _round_cfg_float(_clamp(corridor_q10 * 0.98, min_v=0.01))
    regime["max_corridor_pct"] = _round_cfg_float(max(regime["min_corridor_pct"] + 0.1, corridor_q90 * 1.03))
    regime["min_chop"] = _round_cfg_float(max(1.0, chop_q10 * 0.98))
    base_eff = max(eff_q90 * 1.15, eff_median * 1.35, 0.05)
    regime["max_efficiency_ratio"] = _round_cfg_float(_clamp(base_eff, min_v=0.01, max_v=0.35))
    base_slope = max(slope_q90 * 1.05, slope_median * 1.15, 0.35)
    regime["max_slope_to_corridor_ratio"] = _round_cfg_float(_clamp(base_slope, min_v=0.2, max_v=3.0))

    # PRIMARY: wicks (v9 simplified)
    wicks = filt.setdefault("wicks", {})
    wicks["min_avg_wick_ratio"] = _round_cfg_float(max(0.1, avg_wick_q10 * 0.97))
    wicks["min_wick_count"] = max(1, _floor_int(wick_count_q10 * 0.95))

    # PRIMARY: donchain
    donchain = filt.setdefault("donchain", {})
    donchain["min_donchain_range"] = _round_cfg_float(_clamp(donchain_q10 * 0.97, min_v=0.01))
    donchain["max_donchain_range"] = _round_cfg_float(max(donchain["min_donchain_range"] + 0.1, donchain_q90 * 1.03))

    axis = filt.setdefault("axis", {})
    axis["min_axis_touch_share"] = _round_cfg_float(_clamp(axis_touch_q10 * 0.97, min_v=0.0, max_v=1.0))
    axis["min_recent_axis_touches"] = _floor_int(recent_axis_q10)
    axis["min_rotation_count"] = _floor_int(rotation_q10)

    wall = filt.setdefault("wall", {})
    if recent_wall_median <= 0.01 and recent_wall_q90 <= 0.08:
        wall["min_recent_wall_touch_share"] = 0.0
    else:
        wall["min_recent_wall_touch_share"] = _round_cfg_float(_clamp(recent_wall_q10 * 0.97, min_v=0.0, max_v=1.0))
    wall["min_full_wall_touch_share"] = _round_cfg_float(_clamp(wall_touch_q10 * 0.97, min_v=0.0, max_v=1.0))
    base_cluster = max(wall_cluster_q90 * 1.05, wall_cluster_median * 1.10, 0.10)
    wall["max_cluster_spread_pct"] = _round_cfg_float(_clamp(base_cluster, min_v=0.05, max_v=10.0))

    activity = filt.setdefault("activity", {})
    activity["min_path_to_corridor_ratio"] = _round_cfg_float(max(0.1, path_q10 * 0.97))
    activity["min_return_to_axis_count"] = _floor_int(returns_q10)

    reclaim = filt.setdefault("reclaim", {})
    reclaim["min_false_break_reclaim_share"] = _round_cfg_float(_clamp(reclaim_q10 * 0.97, min_v=0.0, max_v=1.0))

    if float(regime["max_corridor_pct"]) <= float(regime["min_corridor_pct"]):
        regime["max_corridor_pct"] = _round_cfg_float(float(regime["min_corridor_pct"]) + 0.2)
    if float(donchain["max_donchain_range"]) <= float(donchain["min_donchain_range"]):
        donchain["max_donchain_range"] = _round_cfg_float(float(donchain["min_donchain_range"]) + 0.2)
    return filt


def _soften_filter(base_filter: Dict[str, Any]) -> Dict[str, Any]:
    f = _copy_json(base_filter)
    f["min_score_pct"] = _round_cfg_float(float(f.get("min_score_pct", 0.0)) * 0.97)

    regime = f["regime"]
    regime["min_corridor_pct"] = _round_cfg_float(float(regime["min_corridor_pct"]) * 0.97)
    regime["max_corridor_pct"] = _round_cfg_float(float(regime["max_corridor_pct"]) * 1.05)
    regime["min_chop"] = _round_cfg_float(float(regime["min_chop"]) * 0.97)
    regime["max_efficiency_ratio"] = _round_cfg_float(_clamp(float(regime["max_efficiency_ratio"]) * 1.25, min_v=0.01, max_v=0.5))
    regime["max_slope_to_corridor_ratio"] = _round_cfg_float(_clamp(float(regime["max_slope_to_corridor_ratio"]) * 1.12, min_v=0.2, max_v=5.0))

    # PRIMARY: wicks (v9)
    wicks = f["wicks"]
    wicks["min_avg_wick_ratio"] = _round_cfg_float(float(wicks["min_avg_wick_ratio"]) * 0.94)
    wicks["min_wick_count"] = max(1, int(round(int(wicks.get("min_wick_count", 1)) * 0.85)))

    # PRIMARY: donchain
    donchain = f.get("donchain") or {}
    donchain["min_donchain_range"] = _round_cfg_float(float(donchain.get("min_donchain_range", 0.1)) * 0.93)
    donchain["max_donchain_range"] = _round_cfg_float(float(donchain.get("max_donchain_range", 5.0)) * 1.08)
    f["donchain"] = donchain

    axis = f["axis"]
    axis["min_axis_touch_share"] = _round_cfg_float(_clamp(float(axis["min_axis_touch_share"]) * 0.90, min_v=0.0, max_v=1.0))
    axis["min_recent_axis_touches"] = max(0, int(axis["min_recent_axis_touches"]) - 1)
    axis["min_rotation_count"] = max(0, int(round(int(axis["min_rotation_count"]) * 0.82)))

    wall = f["wall"]
    base_recent_wall = float(wall["min_recent_wall_touch_share"])
    wall["min_recent_wall_touch_share"] = 0.0 if base_recent_wall <= 0.03 else _round_cfg_float(base_recent_wall * 0.75)
    wall["min_full_wall_touch_share"] = _round_cfg_float(_clamp(float(wall["min_full_wall_touch_share"]) * 0.85, min_v=0.0, max_v=1.0))
    wall["max_cluster_spread_pct"] = _round_cfg_float(float(wall["max_cluster_spread_pct"]) * 1.15)

    activity = f["activity"]
    activity["min_path_to_corridor_ratio"] = _round_cfg_float(float(activity["min_path_to_corridor_ratio"]) * 0.92)
    activity["min_return_to_axis_count"] = max(0, int(activity["min_return_to_axis_count"]) - 1)

    reclaim = f["reclaim"]
    reclaim["min_false_break_reclaim_share"] = _round_cfg_float(_clamp(float(reclaim["min_false_break_reclaim_share"]) * 0.90, min_v=0.0, max_v=1.0))
    return f


def _tighten_filter(base_filter: Dict[str, Any]) -> Dict[str, Any]:
    f = _copy_json(base_filter)
    f["min_score_pct"] = _round_cfg_float(float(f.get("min_score_pct", 0.0)) * 1.02)

    regime = f["regime"]
    regime["min_corridor_pct"] = _round_cfg_float(float(regime["min_corridor_pct"]) * 1.01)
    regime["max_corridor_pct"] = _round_cfg_float(max(float(regime["min_corridor_pct"]) + 0.1, float(regime["max_corridor_pct"]) * 0.98))
    regime["min_chop"] = _round_cfg_float(float(regime["min_chop"]) * 1.02)
    regime["max_efficiency_ratio"] = _round_cfg_float(_clamp(float(regime["max_efficiency_ratio"]) * 0.85, min_v=0.01, max_v=0.5))
    regime["max_slope_to_corridor_ratio"] = _round_cfg_float(_clamp(float(regime["max_slope_to_corridor_ratio"]) * 0.93, min_v=0.2, max_v=5.0))

    # PRIMARY: wicks (v9)
    wicks = f["wicks"]
    wicks["min_avg_wick_ratio"] = _round_cfg_float(float(wicks["min_avg_wick_ratio"]) * 1.02)
    wicks["min_wick_count"] = max(1, int(round(int(wicks.get("min_wick_count", 1)) * 1.08)))

    # PRIMARY: donchain
    donchain = f.get("donchain") or {}
    donchain["min_donchain_range"] = _round_cfg_float(_clamp(float(donchain.get("min_donchain_range", 0.1)) * 1.03, min_v=0.01))
    donchain["max_donchain_range"] = _round_cfg_float(max(float(donchain["min_donchain_range"]) + 0.1, float(donchain.get("max_donchain_range", 5.0)) * 0.96))
    f["donchain"] = donchain

    axis = f["axis"]
    axis["min_axis_touch_share"] = _round_cfg_float(_clamp(float(axis["min_axis_touch_share"]) * 1.04, min_v=0.0, max_v=1.0))
    axis["min_recent_axis_touches"] = int(axis["min_recent_axis_touches"]) + (1 if int(axis["min_recent_axis_touches"]) > 0 else 0)
    axis["min_rotation_count"] = max(0, _ceil_int(int(axis["min_rotation_count"]) * 1.05))

    wall = f["wall"]
    base_recent_wall = float(wall["min_recent_wall_touch_share"])
    wall["min_recent_wall_touch_share"] = 0.0 if base_recent_wall == 0.0 else _round_cfg_float(_clamp(base_recent_wall * 1.20, min_v=0.0, max_v=1.0))
    wall["min_full_wall_touch_share"] = _round_cfg_float(_clamp(float(wall["min_full_wall_touch_share"]) * 1.05, min_v=0.0, max_v=1.0))
    wall["max_cluster_spread_pct"] = _round_cfg_float(max(0.05, float(wall["max_cluster_spread_pct"]) * 0.90))

    activity = f["activity"]
    activity["min_path_to_corridor_ratio"] = _round_cfg_float(float(activity["min_path_to_corridor_ratio"]) * 1.05)
    activity["min_return_to_axis_count"] = int(activity["min_return_to_axis_count"]) + 1

    reclaim = f["reclaim"]
    reclaim["min_false_break_reclaim_share"] = _round_cfg_float(_clamp(float(reclaim["min_false_break_reclaim_share"]) * 1.05, min_v=0.0, max_v=1.0))
    return f


def _build_ready_slots(summary: Dict[str, Any], cfg_snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    base_filter = _build_base_filter(summary, cfg_snapshot)
    return {
        "soft": _slot_wrapper(_soften_filter(base_filter)),
        "base": _slot_wrapper(base_filter),
        "strict": _slot_wrapper(_tighten_filter(base_filter)),
    }


METRIC_REFERENCE: Dict[str, Dict[str, str]] = {
    "score_pct": {"label": "Общий score", "cfg_path": "filter.min_score_pct", "why": "общая сила совпадения паттерна"},
    "corridor_pct": {"label": "Размер коридора", "cfg_path": "filter.regime.min/max_corridor_pct", "why": "ширина рабочего боковика"},
    "chop": {"label": "Chop", "cfg_path": "filter.regime.min_chop", "why": "насколько цена реально пилит диапазон"},
    "efficiency_ratio": {"label": "Efficiency ratio", "cfg_path": "filter.regime.max_efficiency_ratio", "why": "насколько движение трендовое, а не боковое"},
    "slope_to_corridor_ratio": {"label": "Slope / corridor", "cfg_path": "filter.regime.max_slope_to_corridor_ratio", "why": "наклон диапазона, чтобы не ловить явный тренд"},
    # PRIMARY wicks (v9 simplified)
    "avg_wick_ratio": {"label": "Средняя сила теней (wick ratio)", "cfg_path": "filter.wicks.min_avg_wick_ratio", "why": "(high-low)/abs(open-close) — тени длиннее тела"},
    "wick_count": {"label": "Счётчик wick-свечей", "cfg_path": "filter.wicks.min_wick_count", "why": "количество квалифицированных свечей (pct_range gate + body>0)"},
    "wick_share": {"label": "Доля wick-свечей", "cfg_path": "—", "why": "wick_count / lookback (для справки)"},
    # PRIMARY donchain
    "donchain_range": {"label": "Donchain range %", "cfg_path": "filter.donchain.min/max_donchain_range", "why": "(mean_high/mean_low - 1)*100 за окно"},
    "axis_touch_share": {"label": "Касания оси", "cfg_path": "filter.axis.min_axis_touch_share", "why": "цена часто возвращается к центру"},
    "recent_axis_touch_count": {"label": "Недавние касания оси", "cfg_path": "filter.axis.min_recent_axis_touches", "why": "паттерн активен прямо сейчас"},
    "rotation_count": {"label": "Rotation count", "cfg_path": "filter.axis.min_rotation_count", "why": "сколько раз цена пересекала ось"},
    "recent_wall_touch_share": {"label": "Недавний прижим к стенке", "cfg_path": "filter.wall.min_recent_wall_touch_share", "why": "давит ли цена в стенку сейчас"},
    "wall_touch_share": {"label": "Касания стенки за всё окно", "cfg_path": "filter.wall.min_full_wall_touch_share", "why": "есть ли сама стенка как структура"},
    "wall_cluster_spread_pct": {"label": "Разброс кластера стенки", "cfg_path": "filter.wall.max_cluster_spread_pct", "why": "насколько стенка собрана, а не размазана"},
    "path_to_corridor_ratio": {"label": "Активность внутри диапазона", "cfg_path": "filter.activity.min_path_to_corridor_ratio", "why": "есть ли живое движение вдоль диапазона"},
    "return_to_axis_count": {"label": "Возвраты к оси", "cfg_path": "filter.activity.min_return_to_axis_count", "why": "частота возвращений в центр"},
    "false_break_reclaim_share": {"label": "False-break reclaim", "cfg_path": "filter.reclaim.min_false_break_reclaim_share", "why": "ложные выносы с возвратом"},
}


def _build_reference_ranges(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key in [
        "score_pct",
        "corridor_pct",
        "chop",
        "efficiency_ratio",
        "slope_to_corridor_ratio",
        "avg_wick_ratio",
        "wick_count",
        "wick_share",
        "donchain_range",
        "axis_touch_share",
        "recent_axis_touch_count",
        "rotation_count",
        "recent_wall_touch_share",
        "wall_touch_share",
        "wall_cluster_spread_pct",
        "path_to_corridor_ratio",
        "return_to_axis_count",
        "false_break_reclaim_share",
    ]:
        stats = summary.get(key)
        if not stats:
            continue
        meta = METRIC_REFERENCE.get(key, {})
        out.append(
            {
                "metric": key,
                "label": meta.get("label", key),
                "paste_to": meta.get("cfg_path", ""),
                "why_it_matters": meta.get("why", ""),
                "q10": _round_cfg_float(stats.get("q10", 0.0)),
                "median": _round_cfg_float(stats.get("median", 0.0)),
                "q90": _round_cfg_float(stats.get("q90", 0.0)),
            }
        )
    return out


def _iter_leaf_checks(node: Any, prefix: str = "", enabled: bool = True) -> Iterable[Tuple[str, bool, bool]]:
    if not isinstance(node, dict):
        return
    local_enabled = enabled and bool(node.get("enabled", True))
    if "passed" in node:
        yield prefix, bool(node.get("passed", False)), local_enabled
        return
    for key, value in node.items():
        if key == "enabled":
            continue
        child_prefix = f"{prefix}.{key}" if prefix else key
        yield from _iter_leaf_checks(value, child_prefix, local_enabled)


def _overall_pass(checks: Dict[str, Any]) -> bool:
    leafs = list(_iter_leaf_checks(checks))
    if not leafs:
        return False
    return all(passed for _, passed, is_enabled in leafs if is_enabled)


def _evaluate_filter_on_rows(rows: Sequence[Dict[str, Any]], filter_slot: Dict[str, Any]) -> Dict[str, Any]:
    filter_cfg = ConfigLoader.from_dict({"filter": filter_slot}).filter
    fail_counts: Dict[str, int] = {}
    passed_windows = 0

    for row in rows:
        metrics = row.get("metrics") or {}
        checks = build_filter_checks(filter_cfg, metrics)
        if _overall_pass(checks):
            passed_windows += 1
        for path, passed, is_enabled in _iter_leaf_checks(checks):
            if is_enabled and not passed:
                fail_counts[path] = fail_counts.get(path, 0) + 1

    total = len(rows)
    fail_list = [
        {
            "check": key,
            "fails_in_windows": count,
            "fail_rate_pct": _round(100.0 * count / total, 2) if total else 0.0,
        }
        for key, count in sorted(fail_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "windows_total": total,
        "windows_passed": passed_windows,
        "pass_rate_pct": _round(100.0 * passed_windows / total, 2) if total else 0.0,
        "top_fail_reasons": fail_list[:8],
    }


def _choose_recommended_preset(preset_eval: Dict[str, Dict[str, Any]]) -> str:
    base_rate = float((preset_eval.get("base") or {}).get("pass_rate_pct", 0.0))
    soft_rate = float((preset_eval.get("soft") or {}).get("pass_rate_pct", 0.0))
    strict_rate = float((preset_eval.get("strict") or {}).get("pass_rate_pct", 0.0))
    if base_rate < 20.0 <= soft_rate:
        return "soft"
    if base_rate > 80.0 and strict_rate >= 20.0:
        return "strict"
    return "base"


def _build_quick_guide(recommended_preset: str) -> List[str]:
    return [
        "1. Запусти reverse.py по нужной монете и окну времени.",
        "2. Открой reverse_report_slots.json.",
        f"3. Возьми blocks.{recommended_preset}.filter и замени им объект filter в cfg.json.",
        "4. Запусти main.py и оцени поток кандидатов глазами.",
        "5. Если кандидатов мало — переходи на soft. Если мусора много — переходи на strict.",
    ]


def _build_human_notes(current_eval: Dict[str, Any], preset_eval: Dict[str, Dict[str, Any]], recommended_preset: str) -> List[str]:
    notes: List[str] = []
    curr_rate = float(current_eval.get("pass_rate_pct", 0.0))
    notes.append(f"Текущий cfg пропускает {curr_rate}% окон эталона.")
    notes.append(
        "Профили: "
        f"soft={preset_eval['soft']['pass_rate_pct']}%, "
        f"base={preset_eval['base']['pass_rate_pct']}%, "
        f"strict={preset_eval['strict']['pass_rate_pct']}%."
    )
    notes.append(f"Рекомендованный стартовый слот: {recommended_preset}.")
    return notes


def _build_output_payload(
    *,
    cfg_snapshot: Dict[str, Any],
    symbol_requested: str,
    symbol_used: str,
    timeframe: str,
    lookback: int,
    sample_step_minutes: int,
    start_dt: datetime,
    end_dt: datetime,
    fetch_diag: Dict[str, Any],
    rows: Sequence[Dict[str, Any]],
    skipped: Sequence[Dict[str, Any]],
    endpoints: Sequence[datetime],
    include_full: bool,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    summary = _summary_stats(rows)
    ready_slots = _build_ready_slots(summary, cfg_snapshot)
    current_eval = _evaluate_filter_on_rows(rows, cfg_snapshot.get("filter") or {}) if rows else {
        "windows_total": 0,
        "windows_passed": 0,
        "pass_rate_pct": 0.0,
        "top_fail_reasons": [],
    }
    preset_eval = {
        name: _evaluate_filter_on_rows(rows, slot["filter"]) if rows else {
            "windows_total": 0,
            "windows_passed": 0,
            "pass_rate_pct": 0.0,
            "top_fail_reasons": [],
        }
        for name, slot in ready_slots.items()
    }
    recommended_preset = _choose_recommended_preset(preset_eval)

    slots_payload = {
        "symbol_requested": symbol_requested,
        "symbol_used": symbol_used,
        "exchange": "KUCOIN",
        "timeframe": timeframe,
        "lookback_candles": lookback,
        "sampling_step_minutes": int(sample_step_minutes),
        "window_start_iso": start_dt.isoformat(),
        "window_end_iso": end_dt.isoformat(),
        "recommended_preset": recommended_preset,
        "how_to_use": {
            "paste_target": "cfg.json -> filter",
            "steps": _build_quick_guide(recommended_preset),
        },
        "blocks": ready_slots,
        "copy_paste_json": {
            name: json.dumps(slot, ensure_ascii=False, indent=2)
            for name, slot in ready_slots.items()
        },
    }

    payload: Dict[str, Any] = {
        "symbol_requested": symbol_requested,
        "symbol_used": symbol_used,
        "exchange": "KUCOIN",
        "timeframe": timeframe,
        "lookback_candles": lookback,
        "sampling_step_minutes": int(sample_step_minutes),
        "window_start_iso": start_dt.isoformat(),
        "window_end_iso": end_dt.isoformat(),
        "fetch_diagnostics": fetch_diag,
        "candles_fetched": int(fetch_diag.get("candles_fetched", 0)),
        "samples_total": len(endpoints),
        "samples_computed": len(rows),
        "samples_skipped": list(skipped),
        "recommended_preset": recommended_preset,
        "human_notes": _build_human_notes(current_eval, preset_eval, recommended_preset),
        "quick_guide": _build_quick_guide(recommended_preset),
        "current_cfg_check": current_eval,
        "preset_check": preset_eval,
        "ready_slots": ready_slots,
        "key_reference_ranges": _build_reference_ranges(summary),
        "metrics_summary": summary,
        "suggested_cfg": {
            "filter": ready_slots[recommended_preset]["filter"],
        },
        "note": "reverse.py сначала собирает rolling-окна по эталонной монете, потом считает метрики тем же CalculatingEngine, что и основной скринер. Для вставки в cfg.json используй reverse_report_slots.json.",
    }

    if include_full:
        payload["debug_full"] = {
            "samples": list(rows),
        }
    else:
        payload["debug_full"] = {
            "samples": [],
            "omitted": True,
            "hint": "Запусти reverse.py с --full, если нужны все raw samples и их метрики.",
        }
    return payload, slots_payload


async def run_reverse(
    cfg_path: Path = CFG_PATH,
    out_path: Path = OUT_PATH,
    symbol: str = "WILDUSDT",
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
    sample_step_minutes: int = 5,
    include_full: bool = False,
    slots_out_path: Path | None = None,
    candles_cache_path: Path | None = None,
) -> Dict[str, Any]:
    cfg = load_config(cfg_path)
    cfg_snapshot = cfg.snapshot()
    start_dt = start_dt or _dt_utc(2026, 2, 24, 21, 0)
    end_dt = end_dt or _dt_utc(2026, 2, 25, 0, 35)
    tf_minutes = CandidateTf.to_minutes(cfg.filter.timeframe)
    symbol_norm = _normalize_symbol(symbol)
    lookback = int(cfg.filter.lookback_candles)
    calc = CalculatingEngine(cfg.filter)
    klines_api = KucoinKlines(
        request_interval_sec=max(0.05, float(cfg.app.request_interval_ms) / 1000.0),
        rate_limit_backoff_sec=2.0,
    )

    preload_start = start_dt - timedelta(minutes=lookback * tf_minutes)
    fetch_diag: Dict[str, Any] = {}
    candles: List[Kline] = []
    cache_hit = False
    if candles_cache_path and candles_cache_path.exists():
        try:
            cached = json.loads(candles_cache_path.read_text(encoding="utf-8"))
            rows = cached.get("candles") if isinstance(cached, dict) else []
            candles = [Kline(**row) for row in rows if isinstance(row, dict)]
            cache_hit = bool(candles)
            logger.info(f"reverse candles cache hit: {candles_cache_path}")
        except Exception:
            candles = []

    if not candles:
        try:
            candles = await klines_api.get_klines_range(
                symbol=symbol_norm,
                granularity_min=tf_minutes,
                start_at_ms=int(preload_start.timestamp() * 1000),
                end_at_ms=int(end_dt.timestamp() * 1000),
            )
            if candles_cache_path:
                candles_cache_path.parent.mkdir(parents=True, exist_ok=True)
                candles_cache_path.write_text(
                    json.dumps({"candles": [asdict(k) for k in candles]}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info(f"reverse candles cache saved: {candles_cache_path}")
        finally:
            await klines_api.aclose()
    else:
        await klines_api.aclose()

    fetch_diag = {
        "symbol": symbol_norm,
        "timeframe_minutes": tf_minutes,
        "start_at_ms": int(preload_start.timestamp() * 1000),
        "end_at_ms": int(end_dt.timestamp() * 1000),
        "candles_fetched": len(candles),
        "cache_hit": cache_hit,
        "first_candle_iso": datetime.fromtimestamp(candles[0].ts_ms / 1000, tz=UTC).isoformat() if candles else None,
        "last_candle_iso": datetime.fromtimestamp(candles[-1].ts_ms / 1000, tz=UTC).isoformat() if candles else None,
    }

    endpoints = _window_endpoints(start_dt, end_dt, sample_step_minutes)
    rows: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for dt in endpoints:
        end_ms = int(dt.timestamp() * 1000)
        window = _slice_last(candles, end_ms=end_ms, limit=lookback)
        if len(window) < max(20, lookback // 2):
            skipped.append(
                {
                    "window_end_iso": dt.isoformat(),
                    "reason": f"not enough candles: {len(window)}",
                }
            )
            continue
        summary = calc.summarize(window)
        metrics = asdict(summary)
        rows.append(
            {
                "window_end_iso": dt.isoformat(),
                "symbol": symbol_norm,
                "metrics": metrics,
                "filter_metrics": build_filter_metrics_view(cfg.filter.timeframe, cfg.filter.lookback_candles, metrics),
                "filter_checks": build_filter_checks(cfg.filter, metrics),
            }
        )

    payload, slots_payload = _build_output_payload(
        cfg_snapshot=cfg_snapshot,
        symbol_requested=symbol,
        symbol_used=symbol_norm,
        timeframe=cfg.filter.timeframe,
        lookback=lookback,
        sample_step_minutes=sample_step_minutes,
        start_dt=start_dt,
        end_dt=end_dt,
        fetch_diag=fetch_diag,
        rows=rows,
        skipped=skipped,
        endpoints=endpoints,
        include_full=include_full,
    )

    slots_out = slots_out_path or out_path.with_name(f"{out_path.stem}_slots.json")
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    slots_out.write_text(json.dumps(slots_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"Saved reverse report: {out_path}")
    logger.info(f"Saved copy-paste slots: {slots_out}")
    logger.info(f"Recommended preset: {payload['recommended_preset']}")
    if not candles:
        logger.warning("no candles fetched. Check symbol availability and/or KuCoin API parameter variant.")
    return payload


def _parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reverse-engineer filter metrics for a reference coin and build ready-to-paste cfg slots.")
    p.add_argument("--cfg", type=Path, default=CFG_PATH)
    p.add_argument("--out", type=Path, default=OUT_PATH)
    p.add_argument("--slots-out", type=Path, default=None)
    p.add_argument("--symbol", type=str, default="WILDUSDT")
    p.add_argument("--start", type=str, default="2026-02-24T21:00:00+00:00")
    p.add_argument("--end", type=str, default="2026-02-25T00:35:00+00:00")
    p.add_argument("--step-min", type=int, default=5)
    p.add_argument("--full", action="store_true", help="include all raw samples in reverse_report.json")
    return p.parse_args()


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


if __name__ == "__main__":
    ns = _parse_cli()
    asyncio.run(
        run_reverse(
            cfg_path=ns.cfg,
            out_path=ns.out,
            symbol=ns.symbol,
            start_dt=_parse_dt(ns.start),
            end_dt=_parse_dt(ns.end),
            sample_step_minutes=ns.step_min,
            include_full=bool(ns.full),
            slots_out_path=ns.slots_out,
        )
    )
