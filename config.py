from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, Dict

class ConfigError(RuntimeError): pass

@dataclass
class AppSection:
    quote: str; max_symbols: int; concurrent_symbols: int; top_n: int; request_interval_ms: int; scan_interval_sec: int; screen_once: bool; is_click: bool

@dataclass
class BenchmarkSection:
    enable: bool; target_symbol: str; start_time: str; end_time: str; cache_file: str

@dataclass
class DailyVolumeConfig:
    enable: bool; min_usdt: float; max_usdt: float

@dataclass
class DonchianConfig:
    enable: bool; min_pct: float; max_pct: float

@dataclass
class WicksConfig:
    enable: bool; ratio_threshold: float; candle_range_min_pct: float; min_valid_pct: float

@dataclass
class PenaltyConfig:
    enable: bool; min_range_pct: float; max_penalty_pct: float

@dataclass
class FilterSection:
    timeframe: str; lookback_candles: int
    daily_volume: DailyVolumeConfig; donchian: DonchianConfig; wicks: WicksConfig; narrow_penalty: PenaltyConfig

@dataclass
class AppConfig:
    app: AppSection; benchmark: BenchmarkSection; filter: FilterSection

class ConfigLoader:
    @staticmethod
    def from_dict(user_raw: Dict[str, Any]) -> AppConfig:
        app_d = user_raw.get("app", {})
        bench_d = user_raw.get("benchmark", {})
        filt_d = user_raw.get("filter", {})

        app_cfg = AppSection(
            quote=str(app_d.get("quote", "USDT")).upper().strip(),
            max_symbols=int(app_d.get("max_symbols", 0)),
            concurrent_symbols=int(app_d.get("concurrent_symbols", 5)),
            top_n=int(app_d.get("top_n", 10)),
            request_interval_ms=int(app_d.get("request_interval_ms", 150)),
            scan_interval_sec=int(app_d.get("scan_interval_sec", 600)),
            screen_once=bool(app_d.get("screen_once", True)),
            is_click=bool(app_d.get("is_click", False)),
        )

        bench_cfg = BenchmarkSection(
            enable=bool(bench_d.get("enable", False)),
            target_symbol=str(bench_d.get("target_symbol", "ZIGUSDTM")),
            start_time=str(bench_d.get("start_time", "")),
            end_time=str(bench_d.get("end_time", "")),
            cache_file=str(bench_d.get("cache_file", "benchmark_cache.json")),
        )

        def get_block(name, defaults):
            block = filt_d.get(name, {})
            return {k: type(v)(block.get(k, v)) for k, v in defaults.items()}

        vol_cfg = DailyVolumeConfig(**get_block("daily_volume", {"enable": True, "min_usdt": 500000.0, "max_usdt": 7000000.0}))
        don_cfg = DonchianConfig(**get_block("donchian", {"enable": True, "min_pct": 1.0, "max_pct": 7.0}))
        wicks_cfg = WicksConfig(**get_block("wicks", {"enable": True, "ratio_threshold": 3.0, "candle_range_min_pct": 0.15, "min_valid_pct": 50.0}))
        pen_cfg = PenaltyConfig(**get_block("narrow_penalty", {"enable": True, "min_range_pct": 0.15, "max_penalty_pct": 33.0}))

        filter_cfg = FilterSection(
            timeframe=str(filt_d.get("timeframe", "1m")).lower().strip(),
            lookback_candles=int(filt_d.get("lookback_candles", 30)),
            daily_volume=vol_cfg, donchian=don_cfg, wicks=wicks_cfg, narrow_penalty=pen_cfg
        )

        return AppConfig(app=app_cfg, benchmark=bench_cfg, filter=filter_cfg)

CFG_PATH = "cfg.json"

def load_config(path: str = CFG_PATH) -> AppConfig:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return ConfigLoader.from_dict(json.load(f))
    except Exception as e:
        raise ConfigError(f"Критическая ошибка чтения {path}: {e}")