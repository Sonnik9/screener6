from __future__ import annotations

import asyncio
from pathlib import Path

from benchmark_pipeline import maybe_run_benchmark_calibration
from c_log import UnifiedLogger
from candidates import OUT_PATH as CANDIDATES_OUT_PATH, run_scan
from config import CFG_PATH

logger = UnifiedLogger("main")


async def main(cfg_path: Path = CFG_PATH, out_path: Path = CANDIDATES_OUT_PATH):
    logger.info(f"main start cfg={cfg_path} out={out_path}")
    runtime_cfg_path, calibration_report = await maybe_run_benchmark_calibration(cfg_path=cfg_path)
    extra_payload = {}
    if calibration_report is not None:
        extra_payload["benchmark_calibration"] = calibration_report
    await run_scan(cfg_path=runtime_cfg_path, out_path=out_path, cfg=None, extra_payload=extra_payload)
    logger.info("main finished")


if __name__ == "__main__":
    asyncio.run(main())
