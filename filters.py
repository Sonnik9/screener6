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

            # ==========================================
            # ПУНКТ 2. DONCHIAN (Отношение средних Хаев и Лоев)
            # ==========================================
            avg_high = np.mean(highs)
            avg_low = np.mean(lows)
            
            if avg_low == 0:
                return {"passed": False, "score": -100.0, "reason": "zero_price_error"}
                
            donchian_pct = ((avg_high - avg_low) / avg_low) * 100.0
            
            if not (self.donchian_min <= donchian_pct <= self.donchian_max):
                return {"passed": False, "score": -50.0, "reason": f"donchian_out_of_range ({donchian_pct:.2f}%)"}

            # ==========================================
            # ПУНКТ 3. WICKS ИНДИКАТОР И ПРОГРЕСС
            # ==========================================
            ranges = highs - lows
            bodies = np.abs(opens - closes)
            
            # Маска для защиты от деления на ноль: хай-лой > 0 и опен-клоз > 0
            valid_math_mask = (ranges > 0) & (bodies > 0)
            
            # Расчет пропорции теней к телу. Изначально нули.
            wick_ratios = np.zeros_like(ranges)
            wick_ratios[valid_math_mask] = ranges[valid_math_mask] / bodies[valid_math_mask]
            
            # Расчет размера самой свечи (High-Low) относительно её цены (Low) в %
            lows_safe = np.where(lows == 0, 1e-8, lows)
            candle_pcts = (ranges / lows_safe) * 100.0
            
            # Условия успешной свечи:
            # 1. Пропорция (Тень/Тело) > wick_ratio_threshold
            # 2. Размер самой свечи (High-Low в %) > candle_range_min_pct
            pass_mask = (wick_ratios > self.wick_ratio_threshold) & (candle_pcts > self.candle_range_min_pct)
            
            valid_candles_count = int(np.sum(pass_mask))
            total_candles = len(candles)
            
            # Итоговый прогресс (сколько % свечей оказались штрихами)
            valid_pct = (valid_candles_count / total_candles) * 100.0
            
            if valid_pct < self.min_valid_candles_pct:
                return {
                    "passed": False, 
                    "score": float(valid_pct), 
                    "reason": f"low_wicks_progress ({valid_pct:.1f}% < {self.min_valid_candles_pct}%)"
                }

            # ==========================================
            # УСПЕХ: Скоринг = процент хороших свечей (чем больше штрихов, тем выше в топе)
            # ==========================================
            return {
                "passed": True,
                "score": float(valid_pct),
                "metrics": {
                    "donchian_pct": float(donchian_pct),
                    "valid_wicks_pct": float(valid_pct),
                    "valid_candles_count": valid_candles_count,
                    "total_candles": total_candles
                },
                "reason": "barcode_v2_matched"
            }

        except Exception as e:
            return {"passed": False, "score": -999.0, "reason": f"calc_error: {str(e)}"}