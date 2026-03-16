from __future__ import annotations
import numpy as np
from typing import List, Dict, Any

class CalculatingEngine:
    def __init__(self, filter_cfg):
        self.cfg = filter_cfg

    def analyze(self, candles: List[Any]) -> Dict[str, Any]:
        # Нужен небольшой запас свечей для ATR
        required_len = max(10, self.cfg.atr.period + 1 if self.cfg.atr.enable else 10)
        if not candles or len(candles) < required_len:
            return {"passed": False, "score": -999.0, "reason": "not_enough_candles"}
            
        try:
            def get_val(k, attr, idx): return float(getattr(k, attr, k[idx] if isinstance(k, (list, tuple)) else 0))
            
            # KuCoin Futures индексы: [0:time, 1:open, 2:high, 3:low, 4:close, 5:volume]
            opens = np.array([get_val(k, 'open', 1) for k in candles])
            highs = np.array([get_val(k, 'high', 2) for k in candles])
            lows = np.array([get_val(k, 'low', 3) for k in candles])
            closes = np.array([get_val(k, 'close', 4) for k in candles])

            ranges = np.abs(highs - lows)
            bodies = np.abs(opens - closes)
            lows_safe = np.where(lows == 0, 1e-8, lows)
            candle_pcts = (ranges / lows_safe) * 100.0
            valid_math_mask = (ranges > 0)

            # ==================================
            # 0. ATR (Average True Range) - Волатильность
            # ==================================
            passed_atr = True
            atr_pct = 0.0
            if self.cfg.atr.enable:
                period = self.cfg.atr.period
                prev_closes = np.roll(closes, 1)
                prev_closes[0] = opens[0] 
                
                tr1 = ranges
                tr2 = np.abs(highs - prev_closes)
                tr3 = np.abs(lows - prev_closes)
                true_range = np.maximum(tr1, np.maximum(tr2, tr3))
                
                # SMA от True Range за период (берем конец массива, так как нам нужна текущая волатильность)
                atr_val = np.mean(true_range[-period:]) 
                current_close = closes[-1] if closes[-1] > 0 else 1e-8
                atr_pct = (atr_val / current_close) * 100.0
                passed_atr = self.cfg.atr.min_pct <= atr_pct <= self.cfg.atr.max_pct

            # ==================================
            # 1. КОЭФФИЦИЕНТ МЯСОРУБКИ (Compression Ratio) + Дрейф
            # ==================================
            passed_donchian = True
            donchian_pct = 0.0
            drift_pct = 0.0
            
            if self.cfg.donchian.enable:
                eval_highs = highs[-self.cfg.lookback_candles:]
                eval_lows = lows[-self.cfg.lookback_candles:]
                eval_closes = closes[-self.cfg.lookback_candles:]
                eval_pcts = candle_pcts[-self.cfg.lookback_candles:]
                
                if eval_lows[0] == 0: return {"passed": False, "score": -100.0, "reason": "zero_price"}

                # 1. Считаем Истинный Коридор (отсекаем 5% самых диких шпилек, берем 95-й и 5-й перцентили)
                p95_high = np.percentile(eval_highs, 95)
                p05_low = np.percentile(eval_lows, 5)
                donchian_pct = ((p95_high - p05_low) / p05_low) * 100.0
                
                # 2. Считаем Медианный размер свечи (типичный размах)
                median_candle = np.median(eval_pcts) if len(eval_pcts) > 0 else 0.1
                
                # 3. КОЭФФИЦИЕНТ ШТРИХ-КОДА: Во сколько раз канал больше одной типичной свечи?
                # Для идеального вертолета он должен быть маленьким (от 1.0 до 3.0)
                compression_ratio = donchian_pct / median_candle if median_candle > 0 else 999.0

                # 4. Дрейф (чтобы монета не сползала вниз)
                start_price = eval_closes[0] if eval_closes[0] > 0 else 1e-8
                drift_pct = (np.abs(eval_closes[-1] - start_price) / start_price) * 100.0
                
                # ПРОВЕРКИ:
                # Ширина канала теперь может быть и 10%, главное чтобы Коэффициент был плотным!
                passed_box = self.cfg.donchian.min_pct <= donchian_pct <= self.cfg.donchian.max_pct
                passed_compression = compression_ratio <= 3.0 # Канал не должен превышать среднюю свечу более чем в 3 раза
                passed_drift = drift_pct <= getattr(self.cfg.donchian, 'max_drift_pct', 1.5)
                
                passed_donchian = passed_box and passed_compression and passed_drift

            # ==================================
            # 2. СЧЕТЧИК ШТРАФОВ (Только на целевых свечах)
            # ==================================
            passed_penalty = True
            penalty_pct = 0.0
            if self.cfg.narrow_penalty.enable:
                eval_pcts = candle_pcts[-self.cfg.lookback_candles:]
                eval_math = valid_math_mask[-self.cfg.lookback_candles:]
                
                narrow_mask = (eval_pcts < self.cfg.narrow_penalty.min_range_pct) | (~eval_math)
                penalty_pct = (int(np.sum(narrow_mask)) / len(eval_pcts)) * 100.0
                passed_penalty = penalty_pct <= self.cfg.narrow_penalty.max_penalty_pct

            # ==================================
            # 3. WICKS ИНДИКАТОР (Прогресс)
            # ==================================
            passed_wicks = True
            wicks_progress_pct = 0.0
            if self.cfg.wicks.enable:
                eval_ranges = ranges[-self.cfg.lookback_candles:]
                eval_bodies = bodies[-self.cfg.lookback_candles:]
                eval_pcts = candle_pcts[-self.cfg.lookback_candles:]
                eval_math = valid_math_mask[-self.cfg.lookback_candles:]
                
                with np.errstate(divide='ignore', invalid='ignore'):
                    wick_ratios = np.where(eval_bodies == 0, np.inf, eval_ranges / eval_bodies)
                
                ratio_ok = wick_ratios > self.cfg.wicks.ratio_threshold
                range_ok = eval_pcts >= self.cfg.wicks.candle_range_min_pct
                
                pass_mask = eval_math & ratio_ok & range_ok
                wicks_progress_pct = (int(np.sum(pass_mask)) / len(eval_ranges)) * 100.0
                passed_wicks = wicks_progress_pct >= self.cfg.wicks.min_valid_pct

            # ИТОГ
            is_strict_pass = passed_donchian and passed_penalty and passed_wicks and passed_atr
            
            # Скор формируем так: награждаем за высокий ATR (движение) и штрафуем за широкий Donchian (уход от оси)
            score = float(wicks_progress_pct + (atr_pct * 10) - donchian_pct - penalty_pct)
            if not passed_donchian: score -= 30.0 
            if not passed_atr: score -= 30.0

            return {
                "passed": is_strict_pass,
                "score": score,
                "metrics": {
                    "donchian_pct": float(donchian_pct),
                    "wicks_progress_pct": float(wicks_progress_pct),
                    "penalty_pct": float(penalty_pct),
                    "atr_pct": float(atr_pct)
                },
                "reason": "strict_match" if is_strict_pass else "rejected/approximate"
            }
        except Exception as e:
            return {"passed": False, "score": -999.0, "reason": f"calc_error: {str(e)}"}