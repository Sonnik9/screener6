from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from config import CFG_PATH, AppConfig, load_config
from reverse import run_reverse
from time_helper import parse_utc_to_ms
from c_log import UnifiedLogger

ROOT = Path(__file__).resolve().parent

UTC = timezone.utc
VALID_SLOTS = {"soft", "base", "strict"}
logger = UnifiedLogger("benchmark_pipeline")


class CalibrationError(RuntimeError):
    pass


def _copy_json(obj: Any) -> Any:
    return json.loads(json.dumps(obj))


def _dt_from_any(value: Any, fallback: str | None = None) -> datetime:
    raw = value if value not in (None, "") else fallback
    if raw in (None, ""):
        raise CalibrationError("benchmark requires start/end time")
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(int(raw) / 1000, tz=UTC)
    if isinstance(raw, str):
        s = raw.strip()
        if s.isdigit():
            return datetime.fromtimestamp(int(s) / 1000, tz=UTC)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    raise CalibrationError(f"unsupported datetime value: {value!r}")


def _average_numeric_values(values: List[Any], template_value: Any) -> Any:
    valid = [v for v in values if v is not None]
    if not valid:
        return template_value
    if isinstance(template_value, bool):
        return bool(valid[0])
    if isinstance(template_value, int) and not isinstance(template_value, bool):
        return int(round(sum(float(v) for v in valid) / len(valid)))
    if isinstance(template_value, float):
        return float(sum(float(v) for v in valid) / len(valid))
    return valid[0]


def _average_tree(nodes: List[Any], template: Any) -> Any:
    valid_nodes = [node for node in nodes if node is not None]
    if isinstance(template, dict):
        out: Dict[str, Any] = {}
        for key, value in template.items():
            out[key] = _average_tree([node.get(key) if isinstance(node, dict) else None for node in valid_nodes], value)
        return out
    return _average_numeric_values(valid_nodes, template)


def _build_filter_from_benchmarks(filters: Sequence[Dict[str, Any]], base_filter_template: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate filters from reverse slots without falling back to hardcoded defaults.

    `base_filter_template` must come from current runtime cfg (merged user config),
    so missing fields preserve current working values instead of DEFAULT_CFG values.
    """
    if not filters:
        raise CalibrationError("no benchmark filters to aggregate")
    template = _copy_json(base_filter_template or {})
    if not isinstance(template, dict) or not template:
        raise CalibrationError("base filter template is empty")
    return _average_tree(list(filters), template)


def _normalize_slot_name(raw: Any, *, default: str = "base") -> str:
    slot = str(raw or default).strip().lower()
    if slot not in VALID_SLOTS:
        raise CalibrationError(f"benchmark slot must be one of: {', '.join(sorted(VALID_SLOTS))}")
    return slot


def _normalize_benchmark_item(item: Dict[str, Any], default_step_min: int, default_slot: str) -> Dict[str, Any]:
    symbol = str(item.get("symbol") or "").strip()
    if not symbol:
        raise CalibrationError("benchmark symbol is required")
    start_dt = _dt_from_any(item.get("start_ms") if item.get("start_ms") is not None else item.get("start"))
    end_dt = _dt_from_any(item.get("end_ms") if item.get("end_ms") is not None else item.get("end"))
    if end_dt <= start_dt:
        raise CalibrationError(f"benchmark end must be > start for {symbol}")
    slot = item.get("slot")
    if slot in (None, ""):
        slot = item.get("preset")
    return {
        "symbol": symbol,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "step_min": max(1, int(item.get("step_min") or default_step_min)),
        "slot": _normalize_slot_name(slot, default=default_slot),
    }


async def maybe_run_benchmark_calibration(
    cfg_path: Path = CFG_PATH,
) -> Tuple[AppConfig, Dict[str, Any] | None]:
    cfg = load_config(cfg_path)
    reverse_cfg = cfg.reverse
    raw = cfg.raw or {}
    reverse_raw = raw.get("reverse") or {}
    benchmarks_raw = reverse_raw.get("benchmarks") or []

    if not bool(reverse_cfg.enabled):
        logger.info("reverse.enabled=false -> using cfg.json filter as-is")
        return cfg, None
    if not isinstance(benchmarks_raw, list) or not benchmarks_raw:
        logger.info("reverse.enabled=true but no benchmarks -> using cfg.json filter as-is")
        return cfg, None

    logger.info(f"benchmark calibration started: benchmarks={len(benchmarks_raw)}")

    default_step_min = max(1, int(reverse_cfg.step_min or 5))
    default_slot = _normalize_slot_name(reverse_cfg.slot, default="base")
    benchmark_specs = [_normalize_benchmark_item(item or {}, default_step_min, default_slot) for item in benchmarks_raw]

    selected_filters: List[Dict[str, Any]] = []
    benchmark_reports: List[Dict[str, Any]] = []
    report_dir = cfg_path.parent / "reverse_runs"
    report_dir.mkdir(parents=True, exist_ok=True)

    for idx, spec in enumerate(benchmark_specs, start=1):
        out_name = f"reverse_{idx:02d}_{spec['symbol'].upper()}.json"
        slots_name = f"reverse_{idx:02d}_{spec['symbol'].upper()}_slots.json"
        payload = await run_reverse(
            cfg_path=cfg_path,
            out_path=report_dir / out_name,
            symbol=spec["symbol"],
            start_dt=spec["start_dt"],
            end_dt=spec["end_dt"],
            sample_step_minutes=spec["step_min"],
            include_full=False,
            slots_out_path=report_dir / slots_name,
            candles_cache_path=report_dir / f"candles_{spec['symbol'].upper()}_{spec['start_dt'].strftime('%Y%m%dT%H%M%S')}_{spec['end_dt'].strftime('%Y%m%dT%H%M%S')}_{spec['step_min']}m.json",
        )
        ready_slots = payload.get("ready_slots") or {}
        slot = (ready_slots.get(spec["slot"]) or {}).get("filter")
        if not isinstance(slot, dict):
            raise CalibrationError(f"reverse did not return filter slot for {spec['symbol']} slot={spec['slot']}")
        selected_filters.append(slot)
        benchmark_reports.append(
            {
                "symbol": spec["symbol"],
                "symbol_used": payload.get("symbol_used"),
                "slot_requested": spec["slot"],
                "slot_used": spec["slot"],
                "window_start_iso": spec["start_dt"].isoformat(),
                "window_end_iso": spec["end_dt"].isoformat(),
                "window_start_ms": parse_utc_to_ms(spec["start_dt"].isoformat()),
                "window_end_ms": parse_utc_to_ms(spec["end_dt"].isoformat()),
                "samples_computed": payload.get("samples_computed", 0),
                "candles_fetched": payload.get("candles_fetched", 0),
                "recommended_preset": payload.get("recommended_preset"),
                "report_file": str((report_dir / out_name).name),
                "slots_file": str((report_dir / slots_name).name),
                "slot_filter": slot,
            }
        )

    runtime_filter_template = _copy_json(cfg.snapshot().get("filter") or {})
    auto_filter = _build_filter_from_benchmarks(selected_filters, runtime_filter_template)

    cfg_raw = _copy_json(raw)
    cfg_raw["filter"] = auto_filter
    cfg_path.write_text(json.dumps(cfg_raw, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("cfg.json updated with reverse-computed filter")

    report_payload = {
        "mode": "reverse_then_scan",
        "benchmarks_enabled": True,
        "benchmarks_total": len(benchmark_reports),
        "benchmarks": benchmark_reports,
        "time_helper_hint": {
            "iso_to_ms_example": "python time_helper.py to-ms 2026-02-24T21:00:00+00:00",
            "ms_to_iso_example": "python time_helper.py to-iso 1771966800000",
        },
        "aggregate": {
            "slot_default": default_slot,
            "filter_source": "reverse_computed_from_benchmarks",
            "fallback_template_source": "runtime_cfg.filter",
            "filter": auto_filter,
            "benchmark_symbols": [row["symbol"] for row in benchmark_reports],
            "benchmark_symbol_windows": [
                {
                    "symbol": row["symbol"],
                    "start_ms": row["window_start_ms"],
                    "end_ms": row["window_end_ms"],
                    "start_iso": row["window_start_iso"],
                    "end_iso": row["window_end_iso"],
                    "slot": row["slot_used"],
                }
                for row in benchmark_reports
            ],
        },
    }

    cfg = load_config(cfg_path)
    logger.info("benchmark calibration finished")
    return cfg, report_payload
