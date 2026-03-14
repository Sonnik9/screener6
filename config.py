from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, Dict

class ConfigError(RuntimeError):
    pass

@dataclass
class AppSection:
    quote: str
    max_symbols: int
    concurrent_symbols: int
    top_n: int
    request_interval_ms: int
    scan_interval_sec: int
    screen_once: bool
    is_click: bool

@dataclass
class FilterSection:
    timeframe: str
    lookback_candles: int
    daily_volume_min_usdt: float
    daily_volume_max_usdt: float
    donchian_min_pct: float
    donchian_max_pct: float
    wick_ratio_threshold: float
    candle_range_min_pct: float
    min_valid_candles_pct: float

@dataclass
class AppConfig:
    app: AppSection
    filter: FilterSection

class ConfigLoader:
    @staticmethod
    def from_dict(user_raw: Dict[str, Any]) -> AppConfig:
        app_d = user_raw.get("app", {})
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

        filter_cfg = FilterSection(
            timeframe=str(filt_d.get("timeframe", "1m")).lower().strip(),
            lookback_candles=int(filt_d.get("lookback_candles", 30)),
            daily_volume_min_usdt=float(filt_d.get("daily_volume_min_usdt", 500000.0)),
            daily_volume_max_usdt=float(filt_d.get("daily_volume_max_usdt", 7000000.0)),
            donchian_min_pct=float(filt_d.get("donchian_min_pct", 1.0)),
            donchian_max_pct=float(filt_d.get("donchian_max_pct", 7.0)),
            wick_ratio_threshold=float(filt_d.get("wick_ratio_threshold", 3.0)),
            candle_range_min_pct=float(filt_d.get("candle_range_min_pct", 0.15)),
            min_valid_candles_pct=float(filt_d.get("min_valid_candles_pct", 50.0))
        )

        return AppConfig(app=app_cfg, filter=filter_cfg)

CFG_PATH = "cfg.json"

def load_config(path: str = CFG_PATH) -> AppConfig:
    try:
        with open(path, "r", encoding="utf-8") as f:
            user_raw = json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"КРИТИЧЕСКАЯ ОШИБКА: Файл конфига не найден по пути '{path}'.")
    except json.JSONDecodeError as e:
        raise ConfigError(f"КРИТИЧЕСКАЯ ОШИБКА: Файл '{path}' сломан (ошибка синтаксиса JSON): {e}")
    except Exception as e:
        raise ConfigError(f"Ошибка при чтении конфига: {e}")
        
    return ConfigLoader.from_dict(user_raw)