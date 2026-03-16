import json
import asyncio
import itertools
from pathlib import Path
from c_log import UnifiedLogger
from config import load_config, CFG_PATH
from filters import CalculatingEngine
from KUCOIN.klines import KucoinKlines

logger = UnifiedLogger("benchmark")

async def run_autotune(cfg_path: str = CFG_PATH):
    cfg = load_config(cfg_path)
    if not cfg.benchmark.enable:
        return

    logger.info(f"⚡ БЕНЧМАРК: Автоподгон под {cfg.benchmark.target_symbol}...")
    cache_file = Path(cfg.benchmark.cache_file)
    candles = []

    # 1. Загрузка или парсинг кэша
    if cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                candles = json.load(f)
            logger.info("⚡ БЕНЧМАРК: Свечи загружены из кэша.")
        except: pass

    if not candles:
        logger.info("⚡ БЕНЧМАРК: Кэш пуст. Скачиваем свечи...")
        api = KucoinKlines()
        try:
            candles = await api.get_klines(
                symbol=cfg.benchmark.target_symbol, 
                granularity_min=1, # 1m
                limit=cfg.benchmark.lookback_candles
            )
            with open(cache_file, "w") as f:
                json.dump(candles, f)
        finally:
            await api.aclose()

    if not candles:
        logger.error("⚡ БЕНЧМАРК: Не удалось получить свечи.")
        return

    # 2. Сетка параметров для подгона
    wicks_thresholds = [1.5, 2.0, 2.5, 3.0, 3.5]
    narrow_p_pcts = [20.0, 33.0, 45.0, 60.0]
    
    best_score = -999
    best_params = None

    # Итерация по сетке
    for wt, npp in itertools.product(wicks_thresholds, narrow_p_pcts):
        cfg.filter.wicks.ratio_threshold = wt
        cfg.filter.narrow_penalty.max_penalty_pct = npp
        
        engine = CalculatingEngine(cfg.filter)
        res = engine.analyze(candles[-cfg.filter.lookback_candles:]) # Берем нужное кол-во свечей с конца
        
        if res["passed"] and res["score"] > best_score:
            best_score = res["score"]
            best_params = (wt, npp)

    # 3. Сохранение лучших настроек
    if best_params:
        logger.info(f"⚡ БЕНЧМАРК: Найдены идеальные параметры! Wicks: {best_params[0]}, Max Penalty: {best_params[1]}%")
        with open(cfg_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
        raw_data["filter"]["wicks"]["ratio_threshold"] = best_params[0]
        raw_data["filter"]["narrow_penalty"]["max_penalty_pct"] = best_params[1]
        
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dumps(raw_data, f, indent=4)
    else:
        logger.warning("⚡ БЕНЧМАРК: Эталон не прошел даже при мягких настройках. Попробуйте сменить цель.")