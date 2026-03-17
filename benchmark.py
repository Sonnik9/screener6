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

    logger.info(f"⚡ БЕНЧМАРК (v14.1): Снятие мерок с эталона {cfg.benchmark.target_symbol}...")
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

    target_start_ms = parse_to_ms_utc(cfg.benchmark.start_time)
    target_candles = [c for c in candles if float(c[0]) >= target_start_ms]
    
    if not target_candles:
        logger.error("⚡ БЕНЧМАРК: Провал. В целевом окне нет свечей.")
        return

    def get_val(k, idx): return float(k[idx])
    
    opens_all = np.array([get_val(k, 1) for k in candles])
    highs_all = np.array([get_val(k, 2) for k in candles])
    lows_all = np.array([get_val(k, 3) for k in candles])
    closes_all = np.array([get_val(k, 4) for k in candles])
    
    # 1. Расчет ATR
    atr_actual_pct = 0.5
    if len(candles) > cfg.filter.atr.period:
        prev_closes = np.roll(closes_all, 1)
        prev_closes[0] = opens_all[0]
        tr1 = highs_all - lows_all
        tr2 = np.abs(highs_all - prev_closes)
        tr3 = np.abs(lows_all - prev_closes)
        true_range = np.maximum(tr1, np.maximum(tr2, tr3))
        atr_actual = np.mean(true_range[-len(target_candles):])
        current_close = target_candles[-1][4]
        atr_actual_pct = (atr_actual / float(current_close if current_close > 0 else 1)) * 100.0

    # 2. Метрики V14.1 (Ось, Штрих-Дистанция, Пересечения)
    highs = np.array([get_val(k, 2) for k in target_candles])
    lows = np.array([get_val(k, 3) for k in target_candles])
    closes = np.array([get_val(k, 4) for k in target_candles])

    dist_actual_pct = 0.0
    crosses_pct = 0.0
    crosses_count = 0

    if len(lows) > 0 and lows[0] > 0:
        high_pctl = cfg.filter.barcode_pattern.high_matches_pctl
        low_pctl = 100.0 - cfg.filter.barcode_pattern.low_matches_pctl
        low_pctl = max(0.0, min(100.0, low_pctl))

        high_horizont = np.percentile(highs, high_pctl)
        low_horizont = np.percentile(lows, low_pctl)

        if low_horizont > 0:
            dist_actual_pct = ((high_horizont - low_horizont) / low_horizont) * 100.0
            
            axis = (high_horizont + low_horizont) / 2.0
            signs = np.sign(closes - axis)
            signs = signs[signs != 0]
            if len(signs) > 1:
                crosses_count = int(np.sum(signs[:-1] != signs[1:]))
        
        crosses_pct = (crosses_count / len(target_candles)) * 100.0

    logger.info(f"⚡ ЭТАЛОН: Дистанция {dist_actual_pct:.2f}%, Пересечений {crosses_pct:.1f}% ({crosses_count} шт.), ATR {atr_actual_pct:.2f}%")
    
    # 3. Формирование новых лимитов на основе эталона
    new_min_dist = max(0.5, round(dist_actual_pct * 0.4, 2))
    new_max_dist = round(dist_actual_pct * 1.8, 2)
    new_min_crosses = max(10.0, round(crosses_pct * 0.5, 2))  # Хотим хотя бы 50% от эталонного кол-ва пересечений
    new_atr_min = max(0.5, round(atr_actual_pct * 0.5, 2))
    new_atr_max = round(atr_actual_pct * 2.5, 2)

    with open(cfg_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # Очистка старого технического долга (NARROW_PENALTY ИСКЛЮЧЕН ИЗ УДАЛЕНИЯ)
    for obsolete_key in ["donchian", "wicks"]:
        if obsolete_key in raw_data.get("filter", {}):
            del raw_data["filter"][obsolete_key]

    # Интеграция новых лимитов
    if "barcode_pattern" not in raw_data["filter"]: 
        raw_data["filter"]["barcode_pattern"] = {}
        
    raw_data["filter"]["barcode_pattern"]["min_dist_pct"] = new_min_dist
    raw_data["filter"]["barcode_pattern"]["max_dist_pct"] = new_max_dist
    raw_data["filter"]["barcode_pattern"]["min_crosses_pct"] = new_min_crosses
    
    if "atr" not in raw_data["filter"]: raw_data["filter"]["atr"] = {}
    raw_data["filter"]["atr"]["min_pct"] = new_atr_min
    raw_data["filter"]["atr"]["max_pct"] = new_atr_max
    
    bm_path = "bm_cfg.json"
    with open(bm_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, indent=4)
        
    logger.info(f"⚡ БЕНЧМАРК: V14.1 конфиг сшит и сохранен в {bm_path}")