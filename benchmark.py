import json
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from c_log import UnifiedLogger
from config import load_config, CFG_PATH
from KUCOIN.klines import KucoinKlines

logger = UnifiedLogger("benchmark")

def parse_to_ms_utc(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

async def fetch_historical_klines(symbol: str, start_str: str, end_str: str) -> list:
    api = KucoinKlines()
    all_candles = []
    try:
        from_ms = parse_to_ms_utc(start_str)
        to_ms = parse_to_ms_utc(end_str)
        current_from = from_ms

        while current_from < to_ms:
            data = await api.get_klines(symbol=symbol, granularity_min=1, from_ms=current_from, to_ms=to_ms)
            if not data: break
            data.sort(key=lambda x: x[0])
            all_candles.extend(data)
            last_candle_time = data[-1][0]
            if last_candle_time <= current_from: break
            current_from = last_candle_time + 60000 
            
        final_candles = [c for c in all_candles if from_ms <= c[0] <= to_ms]
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

    logger.info(f"⚡ БЕНЧМАРК: Снятие мерок с эталона {cfg.benchmark.target_symbol}...")
    cache_file = Path(cfg.benchmark.cache_file)
    candles = []

    if cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                candles = json.load(f)
            logger.info(f"⚡ БЕНЧМАРК: Загружено {len(candles)} свечей из кэша.")
        except: pass

    if not candles:
        logger.info("⚡ БЕНЧМАРК: Кэш пуст. Скачиваем свечи эталона...")
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
        logger.error("⚡ БЕНЧМАРК: Провал. Свечи не получены. Проверь даты в конфиге.")
        return

    # =========================================================
    # ИЗВЛЕЧЕНИЕ ПАРАМЕТРОВ (СЧИТЫВАЕМ С ТЕКУЩЕГО ЭТАЛОНА)
    # =========================================================
    def get_val(k, idx): return float(k[idx])
    
    # ИСПРАВЛЕНО: Формат KuCoin Futures: [time, open, high, low, close, volume]
    opens = np.array([get_val(k, 1) for k in candles])
    highs = np.array([get_val(k, 2) for k in candles])
    lows = np.array([get_val(k, 3) for k in candles])
    closes = np.array([get_val(k, 4) for k in candles])

    # Защита через abs()
    ranges = np.abs(highs - lows)
    bodies = np.abs(opens - closes)
    lows_safe = np.where(lows == 0, 1e-8, lows)
    candle_pcts = (ranges / lows_safe) * 100.0

    # 1. Измеряем Donchian эталона
    avg_high, avg_low = np.mean(highs), np.mean(lows)
    # И тут тоже abs на всякий случай
    donchian_actual = (np.abs(avg_high - avg_low) / avg_low) * 100.0 if avg_low > 0 else 1.0

    # 2. Измеряем Wicks (Медиана отношения теней к телу)
    valid_math = (ranges > 0) & (bodies > 0)
    wick_ratios = np.zeros_like(ranges)
    wick_ratios[valid_math] = ranges[valid_math] / bodies[valid_math]
    
    valid_wicks = wick_ratios[wick_ratios > 0]
    actual_ratio_median = np.median(valid_wicks) if len(valid_wicks) > 0 else 2.0
    
    # 3. Измеряем минимальный размер свечи
    actual_range_median = np.median(candle_pcts)

    # =========================================================
    # ФОРМИРОВАНИЕ И СОХРАНЕНИЕ BM_CFG.JSON
    # =========================================================
    # Делаем коридоры вокруг эталона (с запасом, чтобы он проходил фильтр)
    new_donchian_min = round(max(0.1, donchian_actual * 0.4), 2)
    new_donchian_max = round(donchian_actual * 1.6, 2)
    new_wick_ratio = round(actual_ratio_median * 0.6, 2) # Снижаем порог на 40% от медианы
    new_min_range = round(actual_range_median * 0.3, 2)  # Снижаем минимальный размах на 70% от медианы

    logger.info(f"⚡ БЕНЧМАРК: Метрики -> Donchian: {donchian_actual:.2f}%, Wicks Median: {actual_ratio_median:.2f}, Range Median: {actual_range_median:.2f}%")
    
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
        
    raw_data["filter"]["donchian"]["min_pct"] = new_donchian_min
    raw_data["filter"]["donchian"]["max_pct"] = new_donchian_max
    raw_data["filter"]["wicks"]["ratio_threshold"] = new_wick_ratio
    raw_data["filter"]["wicks"]["candle_range_min_pct"] = new_min_range
    raw_data["filter"]["narrow_penalty"]["min_range_pct"] = new_min_range
    
    # Жестко отключаем предфильтр объема, чтобы эталон не отсеялся из-за дневного неликвида
    raw_data["filter"]["daily_volume"]["enable"] = False
    
    bm_path = "bm_cfg.json"
    with open(bm_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, indent=4)
        
    logger.info(f"⚡ БЕНЧМАРК: Идеальный конфиг сшит и сохранен в {bm_path}")