from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

from config import AppConfig, ConfigError
from filters import CalculatingEngine
from KUCOIN.klines import Kline, KucoinKlines
from KUCOIN.symbol import KucoinSymbols
from reporting import build_filter_checks, build_filter_config_view, build_filter_metrics_view
from c_log import UnifiedLogger


@dataclass(frozen=True)
class SymbolMetrics:
    symbol: str
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
    last_close_distance_to_axis_pct: float
    # Primary wicks (v9)
    avg_wick_ratio: float
    wick_count: int
    wick_share: float
    # Secondary: reclaim
    false_break_reclaim_share: float
    # Primary: donchain
    donchain_range: float
    chop: float
    efficiency_ratio: float
    slope_to_corridor_ratio: float
    path_to_corridor_ratio: float
    wall_side: str
    wall_touch_share: float
    recent_wall_touch_share: float
    recent_top_wall_touch_share: float
    recent_bottom_wall_touch_share: float
    wall_cluster_spread_pct: float
    top_wall_touch_share: float
    bottom_wall_touch_share: float
    top_wall_cluster_spread_pct: float
    bottom_wall_cluster_spread_pct: float
    avg_quote_turnover: float
    score: float
    score_pct: float


logger = UnifiedLogger("scanner_engine")

class CandidateScanner:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.timeframe = self.cfg.filter.timeframe
        self.lookback = int(self.cfg.filter.lookback_candles)
        self.quote = self.cfg.app.quote
        self.max_symbols = int(getattr(self.cfg.app, "max_symbols", 0) or 0)
        self.concurrent_symbols = int(self.cfg.app.concurrent_symbols)
        self.top_n = int(self.cfg.app.top_n)
        self.active_filter_view = build_filter_config_view(self.cfg.filter)

        self.symbols_api = KucoinSymbols()
        self.klines_api = KucoinKlines(
            request_interval_sec=max(0.05, float(self.cfg.app.request_interval_ms) / 1000.0),
            rate_limit_backoff_sec=2.0,
        )
        self.calc = CalculatingEngine(self.cfg.filter)
        logger.info(f"scanner init timeframe={self.timeframe} lookback={self.lookback} quote={self.quote}")

    async def aclose(self) -> None:
        await self.symbols_api.aclose()
        await self.klines_api.aclose()

    @staticmethod
    def _tf_to_minutes(tf: str) -> int:
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
            raise ConfigError(f"Unsupported timeframe: {tf}")
        return mapping[key]

    async def _get_base_klines(self, symbol: str) -> List[Kline]:
        return await self.klines_api.get_klines(
            symbol=symbol,
            granularity_min=self._tf_to_minutes(self.timeframe),
            limit=self.lookback,
        )

    def _build_metrics(self, symbol: str, candles: List[Kline]) -> SymbolMetrics:
        min_required = max(20, self.lookback // 2)
        if len(candles) < min_required:
            raise RuntimeError(f"not enough candles: {len(candles)} < {min_required}")

        summary = self.calc.summarize(candles)
        return SymbolMetrics(symbol=symbol, **asdict(summary))

    def _passes_filters(self, m: SymbolMetrics) -> Tuple[bool, List[str]]:
        fails: List[str] = []
        filt = self.cfg.filter

        if filt.regime.enabled:
            if m.corridor_pct < filt.regime.min_corridor_pct:
                fails.append("corridor_too_narrow")
            if m.corridor_pct > filt.regime.max_corridor_pct:
                fails.append("corridor_too_wide")
            if m.chop < filt.regime.min_chop:
                fails.append("chop")
            if m.efficiency_ratio > filt.regime.max_efficiency_ratio:
                fails.append("trend_efficiency")
            if m.slope_to_corridor_ratio > filt.regime.max_slope_to_corridor_ratio:
                fails.append("slope")

        # PRIMARY: wicks
        if filt.wicks.enabled:
            if m.avg_wick_ratio < filt.wicks.min_avg_wick_ratio:
                fails.append("avg_wick_ratio")
            if m.wick_count < filt.wicks.min_wick_count:
                fails.append("wick_count")

        # PRIMARY: donchain
        if filt.donchain.enabled:
            if m.donchain_range < filt.donchain.min_donchain_range:
                fails.append("donchain_range_too_low")
            if m.donchain_range > filt.donchain.max_donchain_range:
                fails.append("donchain_range_too_high")

        if filt.axis.enabled:
            if m.axis_touch_share < filt.axis.min_axis_touch_share:
                fails.append("axis_touch_share")
            if m.recent_axis_touch_count < filt.axis.min_recent_axis_touches:
                fails.append("recent_axis_touches")
            if m.rotation_count < filt.axis.min_rotation_count:
                fails.append("rotation_count")

        if filt.activity.enabled:
            if m.path_to_corridor_ratio < filt.activity.min_path_to_corridor_ratio:
                fails.append("path_to_corridor")
            if m.return_to_axis_count < filt.activity.min_return_to_axis_count:
                fails.append("return_to_axis")

        if filt.reclaim.enabled and m.false_break_reclaim_share < filt.reclaim.min_false_break_reclaim_share:
            fails.append("false_break_reclaim")

        if filt.wall.enabled:
            if m.recent_wall_touch_share < filt.wall.min_recent_wall_touch_share:
                fails.append("recent_wall_touches")
            if m.wall_touch_share < filt.wall.min_full_wall_touch_share:
                fails.append("wall_touches")
            if m.wall_cluster_spread_pct > filt.wall.max_cluster_spread_pct:
                fails.append("wall_cluster")

        if filt.liquidity.enabled and m.avg_quote_turnover < filt.liquidity.min_avg_quote_turnover:
            fails.append("liquidity")

        score_threshold = float(filt.min_score_pct)
        if filt.approximation.enabled:
            score_threshold = float(filt.approximation.min_match_pct)

        if m.score_pct < score_threshold:
            fails.append("score_pct")

        return (len(fails) == 0, fails)

    def _quick_symbol_view(self, row: Dict[str, Any]) -> Dict[str, Any]:
        metrics = row.get("metrics") or {}
        return {
            "symbol": row["symbol"],
            "score_pct": metrics.get("score_pct", 0.0),
            "corridor_pct": metrics.get("corridor_pct", 0.0),
            "donchain_range": metrics.get("donchain_range", 0.0),
            "avg_wick_ratio": metrics.get("avg_wick_ratio", 0.0),
            "wick_count": metrics.get("wick_count", 0),
            "wall_side": metrics.get("wall_side", "n/a"),
            "recent_wall_touch_share": metrics.get("recent_wall_touch_share", 0.0),
            "rotation_count": metrics.get("rotation_count", 0),
            "path_to_corridor_ratio": metrics.get("path_to_corridor_ratio", 0.0),
            "fail_reasons": row.get("fail_reasons") or [],
        }

    async def _analyze_symbol(self, symbol: str) -> Dict[str, Any]:
        candles = await self._get_base_klines(symbol)
        metrics = self._build_metrics(symbol, candles)
        passed, fail_reasons = self._passes_filters(metrics)
        metrics_dict = asdict(metrics)
        return {
            "symbol": symbol,
            "passed": passed,
            "fail_reasons": fail_reasons,
            "metrics": metrics_dict,
            "filter_metrics": build_filter_metrics_view(self.timeframe, self.lookback, metrics_dict),
            "active_filter": self.active_filter_view,
            "filter_checks": build_filter_checks(self.cfg.filter, metrics_dict),
            "score": metrics.score,
            "sort_key": [
                float(metrics.score_pct),
                float(metrics.donchain_range),
                float(metrics.avg_wick_ratio),
                float(metrics.wick_count),
                -float(metrics.last_close_distance_to_axis_pct),
            ],
        }

    async def scan(self) -> Dict[str, Any]:
        started_at_ms = int(time.time() * 1000)
        symbols = sorted(
            await self.symbols_api.get_perp_symbols(
                quote=self.quote,
                limit=self.max_symbols or None,
            )
        )
        sem = asyncio.Semaphore(self.concurrent_symbols)
        reject_stats: Counter[str] = Counter()

        async def worker(sym: str) -> Dict[str, Any]:
            async with sem:
                try:
                    return await self._analyze_symbol(sym)
                except Exception as e:
                    msg = str(e)
                    if "429000" in msg or "HTTP 429" in msg or "RATE_LIMIT_429" in msg:
                        fail = ["error:rate_limit_429"]
                    else:
                        fail = [f"error:{msg}"]
                    return {
                        "symbol": sym,
                        "passed": False,
                        "fail_reasons": fail,
                        "metrics": None,
                        "score": 0.0,
                        "sort_key": [0.0, 0.0, 0.0, 0.0, 0.0],
                    }

        logger.info(f"scan symbols total={len(symbols)} concurrent={self.concurrent_symbols}")
        rows = await asyncio.gather(*(worker(s) for s in symbols))

        passed_rows: List[Dict[str, Any]] = []
        rejected_rows: List[Dict[str, Any]] = []
        for row in rows:
            reasons = row.get("fail_reasons") or []
            if row.get("passed"):
                passed_rows.append(row)
            else:
                rejected_rows.append(row)
                for reason in reasons:
                    reject_stats[reason] += 1

        def _sorter(row: Dict[str, Any]) -> tuple:
            sk = row.get("sort_key") or [0.0, 0.0, 0.0, 0.0, 0.0]
            return (-float(sk[0]), -float(sk[1]), -float(sk[2]), -float(sk[3]), -float(sk[4]), row["symbol"])

        passed_rows.sort(key=_sorter)
        rejected_rows.sort(key=_sorter)

        candidates = passed_rows[: self.top_n]
        near_misses = []
        for row in rejected_rows:
            metrics = row.get("metrics")
            if metrics is None:
                continue
            near_misses.append(
                {
                    "symbol": row["symbol"],
                    "score": row["score"],
                    "fail_reasons": row.get("fail_reasons") or [],
                    "metrics": metrics,
                    "filter_metrics": row.get("filter_metrics") or {},
                    "active_filter": row.get("active_filter") or {},
                    "filter_checks": row.get("filter_checks") or {},
                }
            )

        top_near_misses = near_misses[: min(12, self.top_n)]
        return {
            "generated_at_ms": int(time.time() * 1000),
            "scan_elapsed_ms": int(time.time() * 1000) - started_at_ms,
            "exchange": "KUCOIN",
            "quote": self.quote,
            "timeframe": self.timeframe,
            "lookback_candles": self.lookback,
            "symbols_total": len(symbols),
            "symbols_passed": len(passed_rows),
            "symbols_rejected": max(0, len(symbols) - len(passed_rows)),
            "reject_stats": dict(reject_stats),
            "cfg_snapshot": self.cfg.snapshot(),
            "active_filter": self.active_filter_view,
            "candidate_symbols": [x["symbol"] for x in candidates],
            "recommended_symbols": [x["symbol"] for x in top_near_misses],
            "candidate_quick_list": [self._quick_symbol_view(x) for x in candidates],
            "recommended_quick_list": [self._quick_symbol_view(x) for x in top_near_misses],
            "candidates": candidates,
            "top_near_misses": top_near_misses,
        }
