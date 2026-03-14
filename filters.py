from __future__ import annotations
import numpy as np
from typing import List, Dict, Any

class CalculatingEngine:
    def __init__(self, filter_cfg):
        self.donchian_min = float(filter_cfg.donchian_min_pct)
        self.donchian_max = float(filter_cfg.donchian_max_pct)
        self.wick_ratio_threshold = float(filter_cfg.wick_ratio_threshold)
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

            # ==================================================
            # ШАГ 2: DONCHIAN (Среднее Хаев и Лоев)
            # ==================================================
            avg_high = np.mean(highs)
            avg_low = np.mean(lows)
            
            if avg_low == 0:
                return {"passed": False, "score": -100.0, "reason": "zero_price"}
                
            donchian_pct = ((avg_high - avg_low) / avg_low) * 100.0
            
            # Проверяем соответствие диапазону
            passed_donchian = self.donchian_min <= donchian_pct <= self.donchian_max

            # ==================================================
            # ШАГ 3: WICKS ИНДИКАТОР И ПРОГРЕСС
            # ==================================================
            ranges = highs - lows
            bodies = np.abs(opens - closes)
            
            # Условие: (high - low) > 0 and abs(open - close) > 0
            valid_math_mask = (ranges > 0) & (bodies > 0)
            
            wick_ratios = np.zeros_like(ranges)
            wick_ratios[valid_math_mask] = ranges[valid_math_mask] / bodies[valid_math_mask]
            
            lows_safe = np.where(lows == 0, 1e-8, lows)
            candle_pcts = (ranges / lows_safe) * 100.0
            
            # Суммируем свечи, где выполнены оба условия
            pass_mask = (wick_ratios > self.wick_ratio_threshold) & (candle_pcts > self.candle_range_min_pct)
            valid_candles = int(np.sum(pass_mask))
            
            progress_pct = (valid_candles / len(candles)) * 100.0
            passed_wicks = progress_pct >= self.min_valid_candles_pct

            # ==================================================
            # СКОРИНГ (Для вывода ближайших топов)
            # ==================================================
            is_strict_pass = passed_donchian and passed_wicks
            
            # Базовый скор - это прогресс штрих-кода
            score = float(progress_pct)
            
            # Если Дончиан вылетел за пределы, мы не убиваем скор в -999, 
            # а просто вычитаем штраф, чтобы она упала ниже идеальных монет.
            if not passed_donchian:
                dist = min(abs(donchian_pct - self.donchian_min), abs(donchian_pct - self.donchian_max))
                score -= float(dist * 5.0)

            return {
                "passed": is_strict_pass,
                "score": score,
                "metrics": {
                    "donchian_pct": float(donchian_pct),
                    "wicks_progress_pct": float(progress_pct),
                    "valid_candles": valid_candles
                },
                "reason": "strict_match" if is_strict_pass else "approximate"
            }

        except Exception as e:
            return {"passed": False, "score": -999.0, "reason": f"calc_error: {str(e)}"}