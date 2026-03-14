from __future__ import annotations
import numpy as np
from typing import List, Dict, Any

class CalculatingEngine:
    def __init__(self, filter_cfg):
        self.donchian_min = float(filter_cfg.donchian_min_pct)
        self.donchian_max = float(filter_cfg.donchian_max_pct)
        
        self.max_body_ratio = float(filter_cfg.max_body_ratio)
        self.candle_range_min_pct = float(filter_cfg.candle_range_min_pct)
        self.min_valid_candles_pct = float(filter_cfg.min_valid_candles_pct)

    def analyze(self, candles: List[Any]) -> Dict[str, Any]:
        if not candles or len(candles) < 10:
            return {"passed": False, "score": -999.0, "reason": "not_enough_candles"}

        try:
            def get_val(k, attr, idx): return float(getattr(k, attr, k[idx] if isinstance(k, (list, tuple)) else 0))
            
            opens = np.array([get_val(k, 'open', 1) for k in candles])
            closes = np.array([get_val(k, 'close', 2) for k in candles])
            highs = np.array([get_val(k, 'high', 3) for k in candles])
            lows = np.array([get_val(k, 'low', 4) for k in candles])

            # --- ЗАЩИТА ОТ ДЫРЯВЫХ ГРАФИКОВ ---
            ranges = highs - lows
            bodies = np.abs(opens - closes)
            
            if (np.sum(ranges == 0) / len(candles)) > 0.1:
                return {"passed": False, "score": -50.0, "reason": "dead_chart_gaps"}

            # --- 1. ИСТИННЫЙ DONCHIAN (Ширина всего канала за 30 свечей) ---
            window_max = np.max(highs)
            window_min = np.min(lows)
            
            if window_min == 0:
                return {"passed": False, "score": -100.0, "reason": "zero_price"}
                
            true_donchian_pct = ((window_max - window_min) / window_min) * 100.0
            
            donchian_penalty = 0.0
            if true_donchian_pct < self.donchian_min:
                donchian_penalty = (self.donchian_min - true_donchian_pct) * 10.0
            elif true_donchian_pct > self.donchian_max:
                donchian_penalty = (true_donchian_pct - self.donchian_max) * 10.0

            # --- 2. ТРЕНД И ПЕРЕСЕЧЕНИЯ ОСИ (Главный секрет Пилы) ---
            # Насколько цена ушла от начала окна к концу
            trend_pct = (abs(closes[-1] - closes[0]) / closes[0]) * 100.0
            trend_penalty = trend_pct * 10.0  # Жесткий штраф за любой тренд
            
            # Считаем пересечения центральной оси (туда-сюда)
            axis = np.mean(closes)
            crossings = np.sum((lows <= axis) & (highs >= axis))
            crossings_bonus = (crossings / len(candles)) * 20.0 # Даем бонус за густоту "запила"

            # --- 3. ДОДЖИ-МАТЕМАТИКА (WICKS) ---
            safe_ranges = np.where(ranges == 0, 1e-8, ranges)
            body_ratios = bodies / safe_ranges
            lows_safe = np.where(lows == 0, 1e-8, lows)
            candle_pcts = (ranges / lows_safe) * 100.0
            
            # "Хорошие" штрихи
            pass_mask = (body_ratios <= self.max_body_ratio) & (candle_pcts >= self.candle_range_min_pct)
            valid_pct = (int(np.sum(pass_mask)) / len(candles)) * 100.0
            
            # "Плохие" свечи (жирные импульсы). Если они есть - это не боковик.
            fat_candles = np.sum((body_ratios > 0.6) & (candle_pcts > self.candle_range_min_pct * 1.5))
            fat_penalty = fat_candles * 15.0 # Убиваем скор за каждую жирную свечу

            # --- 4. ИТОГОВЫЙ SCORE ---
            # База = % идеальных доджи + бонус за пилу
            base_score = valid_pct + crossings_bonus
            
            # Вычитаем все пенальти
            score = float(base_score - donchian_penalty - trend_penalty - fat_penalty)
            
            passed = (valid_pct >= self.min_valid_candles_pct) and (donchian_penalty == 0) and (trend_penalty < 10.0) and (fat_candles == 0)

            return {
                "passed": passed,
                "score": score,
                "metrics": {
                    "donchian_pct": float(true_donchian_pct),
                    "valid_wicks_pct": float(valid_pct),
                    "trend_pct": float(trend_pct),
                    "fat_candles": int(fat_candles)
                },
                "reason": "perfect" if passed else "soft_match"
            }

        except Exception as e:
            return {"passed": False, "score": -999.0, "reason": f"calc_error: {str(e)}"}