import json
import asyncio
import itertools
from datetime import datetime
from pathlib import Path
from c_log import UnifiedLogger
from config import load_config, CFG_PATH
from filters import CalculatingEngine
from KUCOIN.klines import KucoinKlines

logger = UnifiedLogger("benchmark")

async def fetch_historical_klines(symbol: str, start_str: str, end_str: str) -> list:
    # ИСПОЛЬЗУЕМ НАШ ЗАКОННЫЙ КЛИЕНТ!
    api = KucoinKlines()
    try:
        dt_start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        dt_end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
        
        from_ms = int(dt_start.timestamp() * 1000)
        to_ms = int(dt_end.timestamp() * 1000)
        
        return await api.get_klines(
            symbol=symbol,
            granularity_min=1, # 1m TF
            from_ms=from_ms,
            to_ms=to_ms
        )
    except Exception as e:
        logger.error(f"Ошибка загрузки истории через клиент: {e}")
        return []
    finally:
        await api.aclose()

async def run_autotune(cfg_path: str = CFG_PATH):
    cfg = load_config(cfg_path)
    if not cfg.benchmark.enable:
        return

    logger.info(f"⚡ БЕНЧМАРК: Автоподгон под {cfg.benchmark.target_symbol} ({cfg.benchmark.start_time} - {cfg.benchmark.end_time})")
    cache_file = Path(cfg.benchmark.cache_file)
    candles = []

    if cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                candles = json.load(f)
            logger.info("⚡ БЕНЧМАРК: Свечи эталона загружены из кэша.")
        except: pass

    if not candles:
        logger.info("⚡ БЕНЧМАРК: Кэш пуст. Скачиваем исторические свечи через API клиент...")
        candles = await fetch_historical_klines(
            cfg.benchmark.target_symbol, 
            cfg.benchmark.start_time, 
            cfg.benchmark.end_time
        )
        if candles:
            with open(cache_file, "w") as f:
                json.dump(candles, f)

    if not candles:
        logger.error("⚡ БЕНЧМАРК: Провал. Свечи не получены.")
        return

    # Сетка параметров: Wicks Threshold, Wicks Min Range, Penalty Max %
    wicks_thresholds = [1.5, 2.0, 2.5, 3.0]
    wicks_ranges = [0.10, 0.15, 0.20]
    penalty_pcts = [20.0, 33.0, 50.0]
    
    best_score = -999
    best_params = None

    for wt, wr, pp in itertools.product(wicks_thresholds, wicks_ranges, penalty_pcts):
        cfg.filter.wicks.ratio_threshold = wt
        cfg.filter.wicks.candle_range_min_pct = wr
        cfg.filter.narrow_penalty.max_penalty_pct = pp
        
        engine = CalculatingEngine(cfg.filter)
        res = engine.analyze(candles)
        
        if res["passed"] and res["score"] > best_score:
            best_score = res["score"]
            best_params = (wt, wr, pp)

    if best_params:
        logger.info(f"⚡ БЕНЧМАРК: Идеал найден! Wicks Ratio: {best_params[0]}, Wicks Range: {best_params[1]}%, Max Penalty: {best_params[2]}%")
        
        with open(cfg_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
        raw_data["filter"]["wicks"]["ratio_threshold"] = best_params[0]
        raw_data["filter"]["wicks"]["candle_range_min_pct"] = best_params[1]
        raw_data["filter"]["narrow_penalty"]["max_penalty_pct"] = best_params[2]
        
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=4)
    else:
        logger.warning("⚡ БЕНЧМАРК: Настройки не подобраны. Эталон не проходит даже мягкие фильтры.")