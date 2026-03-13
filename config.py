from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict


class ConfigError(RuntimeError):
    pass


CFG_TEMPLATE: Dict[str, Any] = {
    "app": {
        "quote": "USDT",
        "max_symbols": 0,
        "concurrent_symbols": 3,
        "top_n": 20,
        "request_interval_ms": 250,
    },
    "exchange": {
        "proxy": "",
        "api_key": "",
        "api_secret": "",
    },
    "benchmark": {
        "enabled": False,
        "step_min": 5,
        "slot": "base",
        "benchmarks": [],
    },
    "filter": {
        "timeframe": "1m",
        "lookback_candles": 120,
        "min_score_pct": 68.0,
        "approximation": {
            "enabled": False,
            "min_match_pct": 100.0,
        },
        "regime": {
            # secondary/optional — geomtry of the sideways: corridor width, choppiness, trendlessness
            "enabled": True,
            "min_corridor_pct": 1.2,
            "max_corridor_pct": 5.6,
            "quantile_low": 0.15,
            "quantile_high": 0.85,
            "min_chop": 56.0,
            "max_efficiency_ratio": 0.38,
            "max_slope_to_corridor_ratio": 0.33,
        },
        "wicks": {
            # PRIMARY — (high-low)/abs(open-close) for candles passing the pct_range gate
            "enabled": True,
            "min_pct_range": 0.3,
            "min_avg_wick_ratio": 2.0,
            "min_wick_count": 10,
        },
        "donchain": {
            # PRIMARY — average range breadth: (mean(highs) / mean(lows) - 1) * 100 over window N
            "enabled": True,
            "window": 20,
            "min_donchain_range": 0.3,
            "max_donchain_range": 5.0,
        },
        "axis": {
            # secondary/optional — mean-reversion axis touches and rotations
            "enabled": True,
            "tolerance_pct": 0.24,
            "recent_window": 24,
            "min_axis_touch_share": 0.18,
            "min_recent_axis_touches": 5,
            "min_rotation_count": 5,
            "mode_bins": 31,
            "use_hlc3": True,
            "close_weight": 0.50,
            "hlc3_weight": 0.50,
        },
        "wall": {
            # secondary/optional — pressure against upper/lower range walls
            "enabled": True,
            "touch_tolerance_pct": 0.35,
            "recent_window": 18,
            "min_recent_wall_touch_share": 0.22,
            "min_full_wall_touch_share": 0.08,
            "top_k_highs": 8,
            "bottom_k_lows": 8,
            "max_cluster_spread_pct": 1.20,
        },
        "activity": {
            # secondary/optional — how actively price moves inside the range
            "enabled": True,
            "min_path_to_corridor_ratio": 4.6,
            "ema_period": 20,
            "axis_band_pct": 0.20,
            "min_return_to_axis_count": 6,
        },
        "reclaim": {
            # secondary/optional — false breakouts with reclaim back inside
            "enabled": True,
            "lookback": 6,
            "min_false_break_reclaim_share": 0.05,
        },
        "liquidity": {
            # secondary/optional — rough liquidity gate
            "enabled": False,
            "min_avg_quote_turnover": 0.0,
        },
    },
}


def _strip_meta_keys(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and k.startswith("_"):
                continue
            cleaned[k] = _strip_meta_keys(v)
        return cleaned
    if isinstance(value, list):
        return [_strip_meta_keys(x) for x in value]
    return value


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class AppSection:
    quote: str = "USDT"
    max_symbols: int = 0
    concurrent_symbols: int = 3
    top_n: int = 20
    request_interval_ms: int = 250


@dataclass
class BenchmarkSection:
    enabled: bool = False
    step_min: int = 5
    slot: str = "base"
    benchmarks: list[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RegimeSection:
    enabled: bool = True
    min_corridor_pct: float = 1.2
    max_corridor_pct: float = 5.6
    quantile_low: float = 0.15
    quantile_high: float = 0.85
    min_chop: float = 56.0
    max_efficiency_ratio: float = 0.38
    max_slope_to_corridor_ratio: float = 0.33


@dataclass
class WicksSection:
    """Primary wicks filter (v9 simplified).

    min_pct_range:     gate — only count candles where (high/low - 1) * 100 >= this.
    min_avg_wick_ratio: filter — avg (high-low)/abs(open-close) >= this.
    min_wick_count:    filter — at least this many qualifying candles.
    """
    enabled: bool = True
    min_pct_range: float = 0.3
    min_avg_wick_ratio: float = 2.0
    min_wick_count: int = 10


@dataclass
class DonchainSection:
    """Primary donchain range filter (v9).

    donchain_range = (mean(highs[-window:]) / mean(lows[-window:]) - 1) * 100
    """
    enabled: bool = True
    window: int = 20
    min_donchain_range: float = 0.3
    max_donchain_range: float = 5.0


@dataclass
class AxisSection:
    enabled: bool = True
    tolerance_pct: float = 0.24
    recent_window: int = 24
    min_axis_touch_share: float = 0.18
    min_recent_axis_touches: int = 5
    min_rotation_count: int = 5
    mode_bins: int = 31
    use_hlc3: bool = True
    close_weight: float = 0.50
    hlc3_weight: float = 0.50


@dataclass
class WallSection:
    enabled: bool = True
    touch_tolerance_pct: float = 0.35
    recent_window: int = 18
    min_recent_wall_touch_share: float = 0.22
    min_full_wall_touch_share: float = 0.08
    top_k_highs: int = 8
    bottom_k_lows: int = 8
    max_cluster_spread_pct: float = 1.20


@dataclass
class ActivitySection:
    enabled: bool = True
    min_path_to_corridor_ratio: float = 4.6
    ema_period: int = 20
    axis_band_pct: float = 0.20
    min_return_to_axis_count: int = 6


@dataclass
class ReclaimSection:
    enabled: bool = True
    lookback: int = 6
    min_false_break_reclaim_share: float = 0.05


@dataclass
class LiquiditySection:
    enabled: bool = False
    min_avg_quote_turnover: float = 0.0


@dataclass
class ApproximationSection:
    enabled: bool = False
    min_match_pct: float = 100.0


@dataclass
class FilterSection:
    timeframe: str = "1m"
    lookback_candles: int = 120
    min_score_pct: float = 68.0
    approximation: ApproximationSection = field(default_factory=ApproximationSection)
    regime: RegimeSection = field(default_factory=RegimeSection)
    wicks: WicksSection = field(default_factory=WicksSection)
    donchain: DonchainSection = field(default_factory=DonchainSection)
    axis: AxisSection = field(default_factory=AxisSection)
    wall: WallSection = field(default_factory=WallSection)
    activity: ActivitySection = field(default_factory=ActivitySection)
    reclaim: ReclaimSection = field(default_factory=ReclaimSection)
    liquidity: LiquiditySection = field(default_factory=LiquiditySection)


@dataclass
class AppConfig:
    app: AppSection = field(default_factory=AppSection)
    exchange: Dict[str, Any] = field(default_factory=dict)
    benchmark: BenchmarkSection = field(default_factory=BenchmarkSection)
    filter: FilterSection = field(default_factory=FilterSection)
    raw: Dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload.pop("raw", None)
        return payload


class ConfigLoader:
    @staticmethod
    def from_dict(user_raw: Dict[str, Any]) -> AppConfig:
        user_raw = _strip_meta_keys(user_raw or {})
        merged = _deep_merge(CFG_TEMPLATE, user_raw)

        app_d = merged.get("app") or {}
        filt_d = merged.get("filter") or {}

        # ---- benchmark section: read "benchmark", fall back to legacy "reverse" ----
        bm_d = merged.get("benchmark") or merged.get("reverse") or {}
        user_bm_d = user_raw.get("benchmark") or user_raw.get("reverse") or {}

        # ---- Backward compatibility: v4 / v5.x / v6.x ----
        counter_condition_pct = filt_d.get("counter_condition_pct")
        if counter_condition_pct is not None and "min_score_pct" not in (user_raw.get("filter") or {}):
            filt_d["min_score_pct"] = float(counter_condition_pct) * 2.1

        # legacy slot names
        if "slot" not in user_bm_d:
            legacy_slot = user_bm_d.get("preset_mode") or user_bm_d.get("default_preset")
            if legacy_slot is not None:
                bm_d["slot"] = legacy_slot

        old_range = filt_d.get("range_condition") or filt_d.get("range") or {}
        old_spikes = filt_d.get("spikes_condition") or filt_d.get("spikes") or {}
        old_axis = filt_d.get("axis_condition") or {}
        old_mean_rev = filt_d.get("mean_reversion") or {}

        regime_user = filt_d.get("regime") or {}
        if "min_corridor_pct" not in regime_user:
            if old_range.get("min_range_distance_pct") is not None:
                regime_user["min_corridor_pct"] = old_range.get("min_range_distance_pct")
            elif old_range.get("min_effective_range_delta_pct") is not None:
                regime_user["min_corridor_pct"] = old_range.get("min_effective_range_delta_pct")
        filt_d["regime"] = _deep_merge(CFG_TEMPLATE["filter"]["regime"], regime_user)

        # wicks: legacy alias mapping (v6 → v9)
        wicks_user = filt_d.get("wicks") or {}
        legacy_wicks_alias = {
            "min_avg_wick_ratio": old_spikes.get("min_avg_wickiness_ratio"),
        }
        for k, v in legacy_wicks_alias.items():
            if v is not None and k not in wicks_user:
                wicks_user[k] = v
        filt_d["wicks"] = _deep_merge(CFG_TEMPLATE["filter"]["wicks"], wicks_user)

        donchain_user = filt_d.get("donchain") or {}
        filt_d["donchain"] = _deep_merge(CFG_TEMPLATE["filter"]["donchain"], donchain_user)

        axis_user = filt_d.get("axis") or {}
        axis_alias = {
            "tolerance_pct": old_axis.get("touch_tolerance_pct"),
            "recent_window": old_axis.get("recent_window"),
            "min_recent_axis_touches": old_axis.get("min_touches"),
            "close_weight": old_axis.get("close_weight"),
            "hlc3_weight": old_axis.get("hlc3_weight"),
        }
        for k, v in axis_alias.items():
            if v is not None and k not in axis_user:
                axis_user[k] = v
        filt_d["axis"] = _deep_merge(CFG_TEMPLATE["filter"]["axis"], axis_user)

        wall_user = filt_d.get("wall") or {}
        wall_alias = {
            "top_k_highs": old_range.get("top_k_highs"),
            "bottom_k_lows": old_range.get("bottom_k_lows"),
            "max_cluster_spread_pct": max(
                float(old_range.get("max_top_high_cluster_spread_pct") or CFG_TEMPLATE["filter"]["wall"]["max_cluster_spread_pct"]),
                float(old_range.get("max_bottom_low_cluster_spread_pct") or CFG_TEMPLATE["filter"]["wall"]["max_cluster_spread_pct"]),
            ) if old_range else None,
        }
        for k, v in wall_alias.items():
            if v is not None and k not in wall_user:
                wall_user[k] = v
        filt_d["wall"] = _deep_merge(CFG_TEMPLATE["filter"]["wall"], wall_user)

        activity_user = filt_d.get("activity") or {}
        activity_alias = {
            "ema_period": old_mean_rev.get("ema_period"),
            "axis_band_pct": old_mean_rev.get("ema_band_pct"),
            "min_return_to_axis_count": old_mean_rev.get("min_return_to_ema_count"),
        }
        for k, v in activity_alias.items():
            if v is not None and k not in activity_user:
                activity_user[k] = v
        filt_d["activity"] = _deep_merge(CFG_TEMPLATE["filter"]["activity"], activity_user)

        reclaim_user = filt_d.get("reclaim") or {}
        reclaim_alias = {
            "min_false_break_reclaim_share": old_spikes.get("min_false_break_reclaim_share"),
        }
        for k, v in reclaim_alias.items():
            if v is not None and k not in reclaim_user:
                reclaim_user[k] = v
        filt_d["reclaim"] = _deep_merge(CFG_TEMPLATE["filter"]["reclaim"], reclaim_user)

        filt_d["liquidity"] = _deep_merge(CFG_TEMPLATE["filter"]["liquidity"], filt_d.get("liquidity") or {})
        filt_d["approximation"] = _deep_merge(CFG_TEMPLATE["filter"]["approximation"], filt_d.get("approximation") or {})

        cfg = AppConfig(
            app=AppSection(
                quote=str(app_d.get("quote") or "USDT").upper().strip(),
                max_symbols=max(0, int(app_d.get("max_symbols") or 0)),
                concurrent_symbols=max(1, int(app_d.get("concurrent_symbols") or 3)),
                top_n=max(1, int(app_d.get("top_n") or 20)),
                request_interval_ms=max(0, int(app_d.get("request_interval_ms") or 250)),
            ),
            exchange=merged.get("exchange") or {},
            benchmark=BenchmarkSection(
                enabled=bool(bm_d.get("enabled", False)),
                step_min=max(1, int(bm_d.get("step_min") or 5)),
                slot=str(bm_d.get("slot") or "base").strip().lower(),
                benchmarks=list(bm_d.get("benchmarks") or []),
            ),
            filter=FilterSection(
                timeframe=str(filt_d.get("timeframe") or "1m").lower().strip(),
                lookback_candles=max(20, int(filt_d.get("lookback_candles") or 120)),
                min_score_pct=float(filt_d.get("min_score_pct") or 68.0),
                approximation=ApproximationSection(**filt_d["approximation"]),
                regime=RegimeSection(**filt_d["regime"]),
                wicks=WicksSection(**filt_d["wicks"]),
                donchain=DonchainSection(**filt_d["donchain"]),
                axis=AxisSection(**filt_d["axis"]),
                wall=WallSection(**filt_d["wall"]),
                activity=ActivitySection(**filt_d["activity"]),
                reclaim=ReclaimSection(**filt_d["reclaim"]),
                liquidity=LiquiditySection(**filt_d["liquidity"]),
            ),
            raw=merged,
        )
        ConfigLoader._validate(cfg)
        return cfg

    @staticmethod
    def _validate(cfg: AppConfig) -> None:
        if cfg.app.concurrent_symbols <= 0:
            raise ConfigError("app.concurrent_symbols must be > 0")
        if cfg.filter.lookback_candles <= 0:
            raise ConfigError("filter.lookback_candles must be > 0")
        if cfg.filter.regime.min_corridor_pct <= 0:
            raise ConfigError("filter.regime.min_corridor_pct must be > 0")
        if cfg.filter.regime.max_corridor_pct <= cfg.filter.regime.min_corridor_pct:
            raise ConfigError("filter.regime.max_corridor_pct must be > min_corridor_pct")
        if not (0.0 < cfg.filter.regime.quantile_low < cfg.filter.regime.quantile_high < 1.0):
            raise ConfigError("filter.regime quantiles must satisfy 0 < low < high < 1")
        if cfg.filter.axis.mode_bins < 3:
            raise ConfigError("filter.axis.mode_bins must be >= 3")
        if cfg.benchmark.slot not in {"soft", "base", "strict"}:
            raise ConfigError("benchmark.slot must be one of: soft, base, strict")
        if not (0.0 < cfg.filter.approximation.min_match_pct <= 100.0):
            raise ConfigError("filter.approximation.min_match_pct must be in (0, 100]")
        if cfg.filter.donchain.min_donchain_range >= cfg.filter.donchain.max_donchain_range:
            raise ConfigError("filter.donchain.max_donchain_range must be > min_donchain_range")


ROOT = Path(__file__).resolve().parent
CFG_PATH = ROOT / "cfg.json"


def load_config(path: Path = CFG_PATH) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"cfg not found: {path}")
    try:
        user_raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ConfigError(f"failed to read cfg: {e}") from e
    if not isinstance(user_raw, dict):
        raise ConfigError("cfg root must be object")
    return ConfigLoader.from_dict(user_raw)
