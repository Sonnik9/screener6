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

async def fetch_historical_klines(symbol: str, start_ms: int, end_ms: int) -> list:
    api = KucoinKlines()
    all_candles = []
    try:
        current_from = start_ms
        while current_from < end_ms:
            data = await api.get_klines(symbol=symbol, granularity_min=1, from_ms=current_from, to_ms=end_ms)
            if not data: break
            data.sort(key=lambda x: x[0])
            all_candles.extend(data)
            last_candle_time = data[-1][0]
            if last_candle_time <= current_from: break
            current_from = last_candle_time + 60000 
            
        final_candles = [c for c in all_candles if start_ms <= c[0] <= end_ms]
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
        logger.info("⚡ БЕНЧМАРК: Кэш пуст. Скачиваем свечи эталона (с запасом для ATR)...")
        # Делаем запас (буфер) для расчета ATR
        target_start_ms = parse_to_ms_utc(cfg.benchmark.start_time)
        target_end_ms = parse_to_ms_utc(cfg.benchmark.end_time)
        buffer_ms = cfg.filter.atr.period * 60 * 1000 if cfg.filter.atr.enable else 0
        fetch_start_ms = target_start_ms - buffer_ms

        candles = await fetch_historical_klines(
            cfg.benchmark.target_symbol, 
            fetch_start_ms, 
            target_end_ms
        )
        if candles:
            with open(cache_file, "w") as f:
                json.dump(candles, f)
            logger.info(f"⚡ БЕНЧМАРК: Сохранено {len(candles)} свечей в кэш.")

    if not candles:
        logger.error("⚡ БЕНЧМАРК: Провал. Свечи не получены. Проверь даты в конфиге.")
        return

    # Выделяем только целевое окно (без буфера) для основной статистики
    target_start_ms = parse_to_ms_utc(cfg.benchmark.start_time)
    target_candles = [c for c in candles if float(c[0]) >= target_start_ms]
    
    if not target_candles:
        logger.error("⚡ БЕНЧМАРК: Провал. В целевом окне нет свечей.")
        return

    def get_val(k, idx): return float(k[idx])
    
    # Считаем ATR по всему скачанному массиву (включая буфер)
    opens_all = np.array([get_val(k, 1) for k in candles])
    highs_all = np.array([get_val(k, 2) for k in candles])
    lows_all = np.array([get_val(k, 3) for k in candles])
    closes_all = np.array([get_val(k, 4) for k in candles])
    
    atr_actual_pct = 0.5
    if len(candles) > cfg.filter.atr.period:
        prev_closes = np.roll(closes_all, 1)
        prev_closes[0] = opens_all[0]
        tr1 = highs_all - lows_all
        tr2 = np.abs(highs_all - prev_closes)
        tr3 = np.abs(lows_all - prev_closes)
        true_range = np.maximum(tr1, np.maximum(tr2, tr3))
        # Средний ATR на целевом участке
        atr_actual = np.mean(true_range[-len(target_candles):])
        current_close = target_candles[-1][4]
        atr_actual_pct = (atr_actual / float(current_close if current_close > 0 else 1)) * 100.0

    # Остальные метрики считаем ТОЛЬКО по целевому окну
    opens = np.array([get_val(k, 1) for k in target_candles])
    highs = np.array([get_val(k, 2) for k in target_candles])
    lows = np.array([get_val(k, 3) for k in target_candles])
    closes = np.array([get_val(k, 4) for k in target_candles])

    ranges = np.abs(highs - lows)
    bodies = np.abs(opens - closes)
    lows_safe = np.where(lows == 0, 1e-8, lows)
    candle_pcts = (ranges / lows_safe) * 100.0

    avg_high, avg_low = np.mean(highs), np.mean(lows)
    donchian_actual = (np.abs(avg_high - avg_low) / avg_low) * 100.0 if avg_low > 0 else 1.0

    valid_math = (ranges > 0) & (bodies > 0)
    wick_ratios = np.zeros_like(ranges)
    wick_ratios[valid_math] = ranges[valid_math] / bodies[valid_math]
    
    valid_wicks = wick_ratios[wick_ratios > 0]
    actual_ratio_median = np.median(valid_wicks) if len(valid_wicks) > 0 else 2.0
    actual_range_median = np.median(candle_pcts)

    # Генерация лимитов
    new_donchian_min = round(max(0.1, donchian_actual * 0.4), 2)
    new_donchian_max = round(donchian_actual * 1.6, 2)
    new_wick_ratio = round(actual_ratio_median * 0.5, 2) 
    new_min_range = round(actual_range_median * 0.3, 2)
    new_atr_min = round(max(0.05, atr_actual_pct * 0.4), 2)
    new_atr_max = round(atr_actual_pct * 2.5, 2)

    logger.info(f"⚡ БЕНЧМАРК: Donchian: {donchian_actual:.2f}%, Wicks: {actual_ratio_median:.2f}, ATR: {atr_actual_pct:.2f}%")
    
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
        
    raw_data["filter"]["donchian"]["min_pct"] = new_donchian_min
    raw_data["filter"]["donchian"]["max_pct"] = new_donchian_max
    raw_data["filter"]["wicks"]["ratio_threshold"] = new_wick_ratio
    raw_data["filter"]["wicks"]["candle_range_min_pct"] = new_min_range
    raw_data["filter"]["narrow_penalty"]["min_range_pct"] = new_min_range
    
    if "atr" not in raw_data["filter"]: raw_data["filter"]["atr"] = {}
    raw_data["filter"]["atr"]["enable"] = True
    raw_data["filter"]["atr"]["min_pct"] = new_atr_min
    raw_data["filter"]["atr"]["max_pct"] = new_atr_max
    
    bm_path = "bm_cfg.json"
    with open(bm_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, indent=4)
        
    logger.info(f"⚡ БЕНЧМАРК: Идеальный конфиг сшит и сохранен в {bm_path}")