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

            # --- ЗАЩИТА ОТ ДЫРЯВЫХ ГРАФИКОВ (неликвида) ---
            ranges = highs - lows
            bodies = np.abs(opens - closes)
            
            zero_candles_count = np.sum(ranges == 0)
            if (zero_candles_count / len(candles)) > 0.1:  # Если больше 10% свечей - мертвые точки
                return {"passed": False, "score": -50.0, "reason": "dead_chart_gaps"}

            # --- 1. DONCHIAN ---
            avg_high = np.mean(highs)
            avg_low = np.mean(lows)
            
            if avg_low == 0:
                return {"passed": False, "score": -100.0, "reason": "zero_price_error"}
                
            donchian_pct = ((avg_high - avg_low) / avg_low) * 100.0
            
            donchian_penalty = 0.0
            if donchian_pct < self.donchian_min:
                donchian_penalty = (self.donchian_min - donchian_pct) * 5.0
            elif donchian_pct > self.donchian_max:
                donchian_penalty = (donchian_pct - self.donchian_max) * 5.0

            # --- 2. ДОДЖИ-МАТЕМАТИКА (WICKS) ---
            # Избегаем деления на ноль. Если range=0, ставим мизерное число
            safe_ranges = np.where(ranges == 0, 1e-8, ranges)
            
            # Доля тела от всей свечи. (Меньше = длиннее тени. Если Доджи, то 0. Идеально!)
            body_ratios = bodies / safe_ranges
            
            # Размах свечи в % от цены
            lows_safe = np.where(lows == 0, 1e-8, lows)
            candle_pcts = (ranges / lows_safe) * 100.0
            
            # Условие: Тело маленькое (<= max_body_ratio) И размах самой свечи больше минимума
            pass_mask = (body_ratios <= self.max_body_ratio) & (candle_pcts >= self.candle_range_min_pct)
            
            valid_candles_count = int(np.sum(pass_mask))
            total_candles = len(candles)
            
            valid_pct = (valid_candles_count / total_candles) * 100.0
            
            # --- 3. ИТОГОВЫЙ SCORE ---
            score = float(valid_pct - donchian_penalty)
            passed = (valid_pct >= self.min_valid_candles_pct) and (donchian_penalty == 0)

            return {
                "passed": passed,
                "score": score,
                "metrics": {
                    "donchian_pct": float(donchian_pct),
                    "valid_wicks_pct": float(valid_pct),
                    "donchian_penalty": float(donchian_penalty)
                },
                "reason": "perfect" if passed else "soft_match"
            }

        except Exception as e:
            return {"passed": False, "score": -999.0, "reason": f"calc_error: {str(e)}"}