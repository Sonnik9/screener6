from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

from config import CFG_PATH, AppConfig, load_config
from scanner_engine import CandidateScanner


ROOT = Path(__file__).resolve().parent
OUT_PATH = ROOT / "candidates.json"


def _fmt_float(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.00"


async def run_scan(
    cfg_path: Path = CFG_PATH,
    out_path: Path = OUT_PATH,
    cfg: Optional[AppConfig] = None,
    extra_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg_obj = cfg or load_config(cfg_path)
    scanner = CandidateScanner(cfg_obj)
    try:
        payload = await scanner.scan()
    finally:
        await scanner.aclose()

    if extra_payload:
        payload.update(extra_payload)

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    symbols_total = int(payload.get("symbols_total", 0))
    symbols_passed = int(payload.get("symbols_passed", 0))
    symbols_rejected = int(payload.get("symbols_rejected", max(0, symbols_total - symbols_passed)))

    print("=" * 168)
    print(
        f"KUCOIN candidates scan v6.4 | timeframe={scanner.timeframe} | lookback={scanner.lookback} | "
        f"symbols={symbols_total} | passed={symbols_passed} | rejected={symbols_rejected} | "
        f"elapsed_ms={payload.get('scan_elapsed_ms', 0)}"
    )
    print("=" * 168)

    top = payload.get("candidates") or []
    if not top:
        print("No candidates passed filters.")
    else:
        for idx, row in enumerate(top[: min(len(top), 20)], start=1):
            m = row.get("metrics") or {}
            print(
                f"#{idx:02d} {row['symbol']:<14} "
                f"score={_fmt_float(m.get('score_pct'), 2)} "
                f"corridor={_fmt_float(m.get('corridor_pct'), 2)}% "
                f"chop={_fmt_float(m.get('chop'), 1)} "
                f"wicks={_fmt_float(m.get('avg_wick_ratio'), 2)}/{_fmt_float(float(m.get('long_wick_share', 0))*100, 1)}% "
                f"two_side={_fmt_float(float(m.get('two_sided_wick_share', 0))*100, 1)}% "
                f"axis={int(m.get('recent_axis_touch_count', 0))}/{_fmt_float(float(m.get('axis_touch_share', 0))*100, 1)}% "
                f"rot={int(m.get('rotation_count', 0))} "
                f"returns={int(m.get('return_to_axis_count', 0))} "
                f"wall={m.get('wall_side', 'n/a')}:{_fmt_float(float(m.get('recent_wall_touch_share', 0))*100, 1)}% "
                f"path={_fmt_float(m.get('path_to_corridor_ratio'), 2)} "
                f"eff={_fmt_float(m.get('efficiency_ratio'), 3)}"
            )

    reject_stats = payload.get("reject_stats") or {}
    if reject_stats:
        print("Reject stats:")
        for reason, count in sorted(reject_stats.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {reason:<30} {count}")

    near = payload.get("top_near_misses") or []
    if near:
        print("Top near misses:")
        for row in near[: min(len(near), 8)]:
            m = row.get("metrics") or {}
            print(
                f"  {row['symbol']:<14} "
                f"score={_fmt_float(m.get('score_pct'), 2)} "
                f"corridor={_fmt_float(m.get('corridor_pct'), 2)}% "
                f"chop={_fmt_float(m.get('chop'), 1)} "
                f"wall={m.get('wall_side', 'n/a')}:{_fmt_float(float(m.get('recent_wall_touch_share', 0))*100, 1)}% "
                f"fails={','.join(row.get('fail_reasons') or [])}"
            )

    print(f"Saved: {out_path}")
    return payload


if __name__ == "__main__":
    asyncio.run(run_scan())
