from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

class ConfigError(RuntimeError):
    pass

@dataclass
class AppSection:
    quote: str = "USDT"
    max_symbols: int = 0
    concurrent_symbols: int = 3
    top_n: int = 20
    request_interval_ms: int = 250
    scan_interval_sec: int = 30

@dataclass
class FilterSection:
    timeframe: str = "1m"
    lookback_candles: int = 60
    
    # 1. Предфильтр
    daily_volume_days: int = 3
    daily_volume_min_usdt: float = 500000.0
    daily_volume_max_usdt: float = 7000000.0
    
    # 2. Donchian Channel
    donchian_min_pct: float = 1.0
    donchian_max_pct: float = 7.0
    
    # 3. Wicks 
    wick_ratio_threshold: float = 3.0
    candle_range_min_pct: float = 0.15
    min_valid_candles_pct: float = 50.0

@dataclass
class AppConfig:
    app: AppSection = field(default_factory=AppSection)
    filter: FilterSection = field(default_factory=FilterSection)

class ConfigLoader:
    @staticmethod
    def from_dict(user_raw: Dict[str, Any]) -> AppConfig:
        app_d = user_raw.get("app", {})
        filt_d = user_raw.get("filter", {})

        app_cfg = AppSection(
            quote=str(app_d.get("quote", "USDT")).upper().strip(),
            max_symbols=max(0, int(app_d.get("max_symbols", 0))),
            concurrent_symbols=max(1, int(app_d.get("concurrent_symbols", 3))),
            top_n=max(1, int(app_d.get("top_n", 20))),
            request_interval_ms=max(0, int(app_d.get("request_interval_ms", 250))),
            scan_interval_sec=max(5, int(app_d.get("scan_interval_sec", 30))),
        )

        filter_cfg = FilterSection(
            timeframe=str(filt_d.get("timeframe", "1m")).lower().strip(),
            lookback_candles=max(10, int(filt_d.get("lookback_candles", 60))),
            daily_volume_days=max(1, int(filt_d.get("daily_volume_days", 3))),
            daily_volume_min_usdt=float(filt_d.get("daily_volume_min_usdt", 500000.0)),
            daily_volume_max_usdt=float(filt_d.get("daily_volume_max_usdt", 7000000.0)),
            donchian_min_pct=float(filt_d.get("donchian_min_pct", 1.0)),
            donchian_max_pct=float(filt_d.get("donchian_max_pct", 7.0)),
            wick_ratio_threshold=float(filt_d.get("wick_ratio_threshold", 3.0)),
            candle_range_min_pct=float(filt_d.get("candle_range_min_pct", 0.15)),
            min_valid_candles_pct=float(filt_d.get("min_valid_candles_pct", 50.0))
        )

        return AppConfig(app=app_cfg, filter=filter_cfg)

ROOT = Path(__file__).resolve().parent
CFG_PATH = ROOT / "cfg.json"

def load_config(path: Path = CFG_PATH) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"cfg not found: {path}")
    try:
        user_raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ConfigError(f"failed to read cfg: {e}")
    return ConfigLoader.from_dict(user_raw)