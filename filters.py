from __future__ import annotations
import numpy as np
from typing import List, Dict, Any

class CalculatingEngine:
    def __init__(self, filter_cfg):
        self.cfg = filter_cfg

    def analyze(self, candles: List[Any]) -> Dict[str, Any]:
        if not candles or len(candles) < 10:
            return {"passed": False, "score": -999.0, "reason": "not_enough_candles"}
        try:
            def get_val(k, attr, idx): return float(getattr(k, attr, k[idx] if isinstance(k, (list, tuple)) else 0))
            
            # ИСПРАВЛЕНО: Правильные индексы для KuCoin Futures
            opens = np.array([get_val(k, 'open', 1) for k in candles])
            highs = np.array([get_val(k, 'high', 2) for k in candles])
            lows = np.array([get_val(k, 'low', 3) for k in candles])
            closes = np.array([get_val(k, 'close', 4) for k in candles])

            # Защита через abs
            ranges = np.abs(highs - lows)
            bodies = np.abs(opens - closes)
            lows_safe = np.where(lows == 0, 1e-8, lows)
            candle_pcts = (ranges / lows_safe) * 100.0

            # БАЗА: хай должен быть больше лоя
            valid_math_mask = (ranges > 0)

            # ==================================
            # 1. DONCHIAN (Средние Хаи к Лоям)
            # ==================================
            passed_donchian = True
            donchian_pct = 0.0
            if self.cfg.donchian.enable:
                avg_high, avg_low = np.mean(highs), np.mean(lows)
                if avg_low == 0: return {"passed": False, "score": -100.0, "reason": "zero_price"}
                donchian_pct = ((avg_high - avg_low) / avg_low) * 100.0
                passed_donchian = self.cfg.donchian.min_pct <= donchian_pct <= self.cfg.donchian.max_pct

            # ==================================
            # 2. НЕЗАВИСИМЫЙ СЧЕТЧИК ШТРАФОВ
            # ==================================
            passed_penalty = True
            penalty_pct = 0.0
            if self.cfg.narrow_penalty.enable:
                # Штраф: свеча меньше min_range_pct ИЛИ вообще точка (ranges == 0)
                narrow_mask = (candle_pcts < self.cfg.narrow_penalty.min_range_pct) | (~valid_math_mask)
                penalty_pct = (int(np.sum(narrow_mask)) / len(candles)) * 100.0
                passed_penalty = penalty_pct <= self.cfg.narrow_penalty.max_penalty_pct

            # ==================================
            # 3. WICKS ИНДИКАТОР (Прогресс)
            # ==================================
            passed_wicks = True
            wicks_progress_pct = 0.0
            if self.cfg.wicks.enable:
                # Обработка деления на ноль для Идеального Доджи (abs(open-close) == 0)
                with np.errstate(divide='ignore', invalid='ignore'):
                    wick_ratios = np.where(bodies == 0, np.inf, ranges / bodies)
                
                # Условия валидной секции:
                ratio_ok = wick_ratios > self.cfg.wicks.ratio_threshold
                range_ok = candle_pcts >= self.cfg.wicks.candle_range_min_pct
                
                pass_mask = valid_math_mask & ratio_ok & range_ok
                wicks_progress_pct = (int(np.sum(pass_mask)) / len(candles)) * 100.0
                passed_wicks = wicks_progress_pct >= self.cfg.wicks.min_valid_pct

            # ИТОГ
            is_strict_pass = passed_donchian and passed_penalty and passed_wicks
            
            # Базовый скор. Штрафуем рейтинг, если пробиты лимиты (чтобы улетело вниз топа)
            score = float(wicks_progress_pct - penalty_pct)
            if not passed_donchian: score -= 20.0 

            return {
                "passed": is_strict_pass,
                "score": score,
                "metrics": {
                    "donchian_pct": float(donchian_pct),
                    "wicks_progress_pct": float(wicks_progress_pct),
                    "penalty_pct": float(penalty_pct)
                },
                "reason": "strict_match" if is_strict_pass else "rejected/approximate"
            }
        except Exception as e:
            return {"passed": False, "score": -999.0, "reason": f"calc_error: {str(e)}"}