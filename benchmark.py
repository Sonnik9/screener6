import json
import asyncio
import itertools
from datetime import datetime, timezone
from pathlib import Path
from c_log import UnifiedLogger
from config import load_config, CFG_PATH
from filters import CalculatingEngine
from KUCOIN.klines import KucoinKlines

logger = UnifiedLogger("benchmark")

def parse_to_ms_utc(date_str: str) -> int:
    # ЖЕСТКАЯ ПРИВЯЗКА К UTC, чтобы не было смещений по часовым поясам!
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

async def fetch_historical_klines(symbol: str, start_str: str, end_str: str) -> list:
    api = KucoinKlines()
    all_candles = []
    try:
        from_ms = parse_to_ms_utc(start_str)
        to_ms = parse_to_ms_utc(end_str)

        current_from = from_ms

        # Чанковый запрос (как в правильных пайплайнах), на случай длинных периодов
        while current_from < to_ms:
            data = await api.get_klines(
                symbol=symbol,
                granularity_min=1,
                from_ms=current_from,
                to_ms=to_ms
            )
            
            if not data:
                break
                
            # Убеждаемся, что свечи идут от старых к новым (KuCoin иногда отдает задом наперед)
            data.sort(key=lambda x: x[0])
            all_candles.extend(data)
            
            last_candle_time = data[-1][0]
            if last_candle_time <= current_from:
                break # Защита от вечного цикла
                
            current_from = last_candle_time + 60000 # Сдвигаемся на 1 минуту вперед
            
        # Жестко фильтруем ровно то, что просили
        final_candles = [c for c in all_candles if from_ms <= c[0] <= to_ms]
        
        if not final_candles:
            logger.warning("KuCoin вернул пустой список. Возможно, запрошенный период (2024 год) слишком старый и биржа больше не хранит 1m свечи за это время!")
            
        return final_candles
    except Exception as e:
        logger.error(f"Ошибка загрузки истории бенчмарка: {e}")
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
            logger.info(f"⚡ БЕНЧМАРК: Загружено {len(candles)} свечей из кэша.")
        except Exception as e:
            logger.error(f"Ошибка чтения кэша: {e}")

    if not candles:
        logger.info("⚡ БЕНЧМАРК: Кэш пуст. Тянем историю через API чанками...")
        candles = await fetch_historical_klines(
            cfg.benchmark.target_symbol, 
            cfg.benchmark.start_time, 
            cfg.benchmark.end_time
        )
        if candles:
            with open(cache_file, "w") as f:
                json.dump(candles, f)
            logger.info(f"⚡ БЕНЧМАРК: Сохранено {len(candles)} свечей в кэш.")

    if not candles:
        logger.error("⚡ БЕНЧМАРК: Провал. Свечи не получены. ВНИМАНИЕ: Попробуйте изменить дату в cfg.json на более свежую (например, 2 недели назад).")
        return

    wicks_thresholds = [1.5, 2.0, 2.5, 3.0]
    wicks_ranges = [0.10, 0.15, 0.20, 0.25]
    penalty_pcts = [20.0, 33.0, 40.0, 50.0]
    
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
        logger.info(f"⚡ БЕНЧМАРК: Идеал найден! Скор: {best_score:.1f} | Wicks Ratio: {best_params[0]}, Min Range: {best_params[1]}%, Max Penalty: {best_params[2]}%")
        
        with open(cfg_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
        raw_data["filter"]["wicks"]["ratio_threshold"] = best_params[0]
        raw_data["filter"]["wicks"]["candle_range_min_pct"] = best_params[1]
        raw_data["filter"]["narrow_penalty"]["max_penalty_pct"] = best_params[2]
        
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=4)
        logger.info("⚡ БЕНЧМАРК: Конфиг успешно обновлен!")
    else:
        logger.warning("⚡ БЕНЧМАРК: Настройки не подобраны. Эталон не проходит даже мягкие фильтры.")