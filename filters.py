from __future__ import annotations

from typing import List

from filter_models import FilterSummary
from scanner_metrics import (
    AxisStats, CorridorLevels, DonchainStats, RegimeStats, WallStats, WickStats,
    axis_stats, build_corridor, donchain_stats, reclaim_share, regime_stats,
    wall_stats, wick_stats,
)
from KUCOIN.klines import Kline


class CalculatingEngine:
    def __init__(self, filter_cfg):
        self.filter_cfg = filter_cfg

    @staticmethod
    def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, float(v)))

    def _band_score(self, value: float, lo: float, hi: float) -> float:
        if lo <= value <= hi:
            return 1.0
        if value < lo:
            return self._clamp(value / max(lo, 1e-12))
        span = max(hi, 1e-12)
        overshoot = (value - hi) / span
        return self._clamp(1.0 - overshoot)

    def _score(
        self,
        corridor: CorridorLevels,
        w: WickStats,
        a: AxisStats,
        ws: WallStats,
        r: RegimeStats,
        dc: DonchainStats,
        false_break_reclaim: float,
    ) -> float:
        cfg = self.filter_cfg
        regime = cfg.regime
        wick = cfg.wicks
        axis = cfg.axis
        wall = cfg.wall
        activity = cfg.activity
        reclaim = cfg.reclaim
        donchain = cfg.donchain

        # Secondary: regime geometry
        corridor_part = self._band_score(corridor.pct, regime.min_corridor_pct, regime.max_corridor_pct)
        chop_part = self._clamp(r.chop / max(regime.min_chop, 1e-12))
        efficiency_part = self._clamp(1.0 - (r.efficiency_ratio / max(regime.max_efficiency_ratio, 1e-12)))
        slope_part = self._clamp(1.0 - (r.slope_to_corridor_ratio / max(regime.max_slope_to_corridor_ratio, 1e-12)))

        # PRIMARY: wicks (v9 simplified)
        avg_wick_part = self._clamp(w.avg_wick_ratio / max(wick.min_avg_wick_ratio, 1e-12))
        wick_count_part = self._clamp(w.wick_count / max(wick.min_wick_count, 1e-12))

        # Secondary: reclaim
        reclaim_part = self._clamp(false_break_reclaim / max(reclaim.min_false_break_reclaim_share, 1e-12))

        # PRIMARY: donchain range
        donchain_part = self._band_score(dc.donchain_range, donchain.min_donchain_range, donchain.max_donchain_range)

        # Secondary: axis
        axis_touch_part = self._clamp(a.axis_touch_share / max(axis.min_axis_touch_share, 1e-12))
        recent_axis_part = self._clamp(a.recent_axis_touch_count / max(axis.min_recent_axis_touches, 1e-12))
        rotation_part = self._clamp(a.rotation_count / max(axis.min_rotation_count, 1e-12))
        return_part = self._clamp(a.return_to_axis_count / max(activity.min_return_to_axis_count, 1e-12))

        # Secondary: wall
        wall_touch_part = self._clamp(ws.recent_best_touch_share / max(wall.min_recent_wall_touch_share, 1e-12))
        wall_cluster_part = self._clamp(1.0 - (ws.best_cluster_spread_pct / max(wall.max_cluster_spread_pct, 1e-12)))
        path_part = self._clamp(r.path_to_corridor_ratio / max(activity.min_path_to_corridor_ratio, 1e-12))

        # Weights: primary features carry more; sum = 1.17 → score in [0, 100]
        raw_score = (
            0.10 * corridor_part
            + 0.08 * chop_part
            + 0.07 * efficiency_part
            + 0.05 * slope_part
            + 0.14 * avg_wick_part       # PRIMARY (was 0.10)
            + 0.14 * wick_count_part     # PRIMARY (new)
            + 0.05 * reclaim_part        # secondary (was 0.08)
            + 0.10 * donchain_part       # PRIMARY (new)
            + 0.10 * axis_touch_part
            + 0.06 * recent_axis_part
            + 0.07 * rotation_part
            + 0.04 * return_part
            + 0.09 * wall_touch_part
            + 0.03 * wall_cluster_part
            + 0.05 * path_part
        )
        score = raw_score / 1.17
        return round(score * 100.0, 6)

    def summarize(self, candles: List[Kline]) -> FilterSummary:
        if not candles:
            return FilterSummary(
                candles_count=0,
                corridor_low=0.0,
                corridor_high=0.0,
                corridor_mid=0.0,
                corridor_pct=0.0,
                structural_axis=0.0,
                axis_touch_count=0,
                axis_touch_share=0.0,
                recent_axis_touch_count=0,
                recent_axis_touch_share=0.0,
                rotation_count=0,
                return_to_axis_count=0,
                avg_axis_distance_pct=0.0,
                avg_wick_ratio=0.0,
                wick_count=0,
                wick_share=0.0,
                false_break_reclaim_share=0.0,
                donchain_range=0.0,
                chop=0.0,
                efficiency_ratio=1.0,
                slope_to_corridor_ratio=999.0,
                path_to_corridor_ratio=0.0,
                top_wall_touch_share=0.0,
                bottom_wall_touch_share=0.0,
                recent_top_wall_touch_share=0.0,
                recent_bottom_wall_touch_share=0.0,
                wall_side="none",
                wall_touch_share=0.0,
                recent_wall_touch_share=0.0,
                top_wall_cluster_spread_pct=999.0,
                bottom_wall_cluster_spread_pct=999.0,
                wall_cluster_spread_pct=999.0,
                avg_quote_turnover=0.0,
                last_close_distance_to_axis_pct=0.0,
                score=0.0,
                score_pct=0.0,
            )

        corridor = build_corridor(candles, self.filter_cfg.regime.quantile_low, self.filter_cfg.regime.quantile_high)
        w = wick_stats(candles, self.filter_cfg.wicks)
        false_reclaim = reclaim_share(candles, self.filter_cfg.reclaim.lookback)
        dc = donchain_stats(candles, self.filter_cfg.donchain.window)
        a = axis_stats(candles, corridor, self.filter_cfg.axis, self.filter_cfg.activity)
        ws = wall_stats(candles, self.filter_cfg.wall)
        r = regime_stats(candles, corridor)
        score = self._score(corridor, w, a, ws, r, dc, false_reclaim)

        return FilterSummary(
            candles_count=len(candles),
            corridor_low=float(corridor.low),
            corridor_high=float(corridor.high),
            corridor_mid=float(corridor.mid),
            corridor_pct=float(corridor.pct),
            structural_axis=float(a.axis),
            axis_touch_count=int(round(a.axis_touch_share * len(candles))),
            axis_touch_share=float(a.axis_touch_share),
            recent_axis_touch_count=int(a.recent_axis_touch_count),
            recent_axis_touch_share=float(a.recent_axis_touch_share),
            rotation_count=int(a.rotation_count),
            return_to_axis_count=int(a.return_to_axis_count),
            avg_axis_distance_pct=float(a.avg_axis_distance_pct),
            avg_wick_ratio=float(w.avg_wick_ratio),
            wick_count=int(w.wick_count),
            wick_share=float(w.wick_share),
            false_break_reclaim_share=float(false_reclaim),
            donchain_range=float(dc.donchain_range),
            chop=float(r.chop),
            efficiency_ratio=float(r.efficiency_ratio),
            slope_to_corridor_ratio=float(r.slope_to_corridor_ratio),
            path_to_corridor_ratio=float(r.path_to_corridor_ratio),
            top_wall_touch_share=float(ws.top_touch_share),
            bottom_wall_touch_share=float(ws.bottom_touch_share),
            recent_top_wall_touch_share=float(ws.recent_top_touch_share),
            recent_bottom_wall_touch_share=float(ws.recent_bottom_touch_share),
            wall_side=str(ws.best_side),
            wall_touch_share=float(ws.best_touch_share),
            recent_wall_touch_share=float(ws.recent_best_touch_share),
            top_wall_cluster_spread_pct=float(ws.top_cluster_spread_pct),
            bottom_wall_cluster_spread_pct=float(ws.bottom_cluster_spread_pct),
            wall_cluster_spread_pct=float(ws.best_cluster_spread_pct),
            avg_quote_turnover=float(r.avg_quote_turnover),
            last_close_distance_to_axis_pct=float(a.last_close_distance_to_axis_pct),
            score=float(score),
            score_pct=float(score),
        )
