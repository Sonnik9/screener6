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
        # Берем дневной лимит из конфига, чтобы пересчитать его в минутный
        self.daily_volume_min = float(filter_cfg.daily_volume_min_usdt)

    def analyze(self, candles: List[Any]) -> Dict[str, Any]:
        if not candles or len(candles) < 10:
            return {"passed": False, "score": -999.0, "reason": "not_enough_candles"}

        try:
            def get_val(k, attr, idx): return float(getattr(k, attr, k[idx] if isinstance(k, (list, tuple)) else 0))
            
            opens = np.array([get_val(k, 'open', 1) for k in candles])
            closes = np.array([get_val(k, 'close', 2) for k in candles])
            highs = np.array([get_val(k, 'high', 3) for k in candles])
            lows = np.array([get_val(k, 'low', 4) for k in candles])

            # --- 1. ИСТИННЫЙ ОБЪЕМ (TURNOVER USDT) ИЗ 1M СВЕЧЕЙ ---
            # В KuCoin Futures 7-й элемент (индекс 6) это оборот в валюте котировки (USDT)
            def get_turnover(k):
                try:
                    if isinstance(k, (list, tuple)) and len(k) >= 7:
                        return float(k[6])
                    return float(k[2]) * float(k[5]) # Fallback, если биржа отдает обрезку
                except:
                    return 0.0
            
            turnovers = np.array([get_turnover(k) for k in candles])
            avg_1m_turnover = np.mean(turnovers)
            
            # Если средний минутный объем меньше требуемого (например, 500k / 1440 мин = ~347 USDT/мин)
            min_1m_req = self.daily_volume_min / 1440.0
            if avg_1m_turnover < min_1m_req:
                return {"passed": False, "score": -100.0, "reason": f"low_liq ({avg_1m_turnover:.0f} USDT/m)"}

            # --- 2. АНТИ-СРАКА ФИЛЬТР (Защита от мертвых графиков) ---
            ranges = highs - lows
            bodies = np.abs(opens - closes)
            
            # Если больше 15% свечей нулевые (просто точки на графике)
            if np.sum(ranges == 0) > len(candles) * 0.15:
                return {"passed": False, "score": -50.0, "reason": "dead_chart_dots"}
                
            # Защита от пинг-понга (цена бьется между двумя тиками)
            unique_closes = len(np.unique(closes))
            if unique_closes < 5:
                return {"passed": False, "score": -50.0, "reason": f"ping_pong_bot ({unique_closes} prices)"}

            # --- 3. ИСТИННЫЙ DONCHIAN (Ширина канала) ---
            window_max = np.max(highs)
            window_min = np.min(lows)
            
            if window_min == 0:
                return {"passed": False, "score": -100.0, "reason": "zero_price"}
                
            true_donchian_pct = ((window_max - window_min) / window_min) * 100.0
            
            # Если канал шире 5% (или сколько стоит в конфиге) - это памп/дамп, а не боковик
            if true_donchian_pct > self.donchian_max or true_donchian_pct < self.donchian_min:
                 return {"passed": False, "score": -10.0, "reason": f"bad_channel ({true_donchian_pct:.1f}%)"}

            # --- 4. ЗАЩИТА ОТ ТРЕНДА И ПЕРЕСЕЧЕНИЯ ОСИ ---
            trend_pct = (abs(closes[-1] - closes[0]) / closes[0]) * 100.0
            if trend_pct > (true_donchian_pct * 0.5): 
                return {"passed": False, "score": -10.0, "reason": f"trending ({trend_pct:.1f}%)"}
            
            axis = np.mean(closes)
            crossings = np.sum((lows <= axis) & (highs >= axis))
            if crossings < len(candles) * 0.3: # Минимум 30% свечей должны пересекать ось
                 return {"passed": False, "score": -10.0, "reason": f"few_crossings ({crossings})"}

            # --- 5. ДОДЖИ-МАТЕМАТИКА (WICKS) И ЗАЩИТА ОТ СОПЛЕЙ ---
            safe_ranges = np.where(ranges == 0, 1e-8, ranges)
            body_ratios = bodies / safe_ranges
            lows_safe = np.where(lows == 0, 1e-8, lows)
            candle_pcts = (ranges / lows_safe) * 100.0
            
            # Детектор одиночного ликвидационного спайка (сопли)
            max_candle_pct = np.max(candle_pcts)
            if max_candle_pct > (true_donchian_pct * 0.6) and true_donchian_pct > 1.0:
                 return {"passed": False, "score": -20.0, "reason": "massive_spike_detected"}
                 
            # Жирные свечи (полнотелые импульсы)
            fat_candles = np.sum((body_ratios > 0.4) & (candle_pcts > self.candle_range_min_pct))
            if fat_candles > len(candles) * 0.2:
                 return {"passed": False, "score": -10.0, "reason": f"too_many_fat ({fat_candles})"}

            # Считаем идеальные штрихи
            pass_mask = (body_ratios <= self.max_body_ratio) & (candle_pcts >= self.candle_range_min_pct)
            valid_pct = (int(np.sum(pass_mask)) / len(candles)) * 100.0
            
            if valid_pct < self.min_valid_candles_pct:
                 return {"passed": False, "score": -5.0, "reason": f"not_enough_wicks ({valid_pct:.1f}%)"}

            # --- 6. ИТОГОВЫЙ SCORE ---
            score = float(valid_pct + (crossings / len(candles) * 50.0))

            return {
                "passed": True,
                "score": score,
                "metrics": {
                    "donchian_pct": float(true_donchian_pct),
                    "valid_wicks_pct": float(valid_pct),
                    "daily_vol_est": float(avg_1m_turnover * 1440), # Вычисляем эквивалент за 24ч
                    "crossings": int(crossings)
                },
                "reason": "perfect_barcode"
            }

        except Exception as e:
            return {"passed": False, "score": -999.0, "reason": f"calc_error: {str(e)}"}