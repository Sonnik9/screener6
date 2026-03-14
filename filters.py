from __future__ import annotations
import numpy as np
from typing import List, Dict, Any

class CalculatingEngine:
    def __init__(self, filter_cfg):
        self.vol_z_threshold = getattr(filter_cfg, 'vol_z_threshold', 2.0)
        self.price_z_threshold = getattr(filter_cfg, 'price_z_threshold', 1.5)
        self.min_turnover_usdt = getattr(filter_cfg, 'min_turnover_usdt', 5000.0)

    def analyze(self, candles: List[Any]) -> Dict[str, Any]:
        if not candles or len(candles) < 20:
            return {"passed": False, "score": -999.0, "reason": "not_enough_candles"}

        try:
            def get_val(k, attr, idx): return float(getattr(k, attr, k[idx] if isinstance(k, (list, tuple)) else 0))
            
            opens = np.array([get_val(k, 'open', 1) for k in candles])
            closes = np.array([get_val(k, 'close', 2) for k in candles])
            highs = np.array([get_val(k, 'high', 3) for k in candles])
            lows = np.array([get_val(k, 'low', 4) for k in candles])
            volumes = np.array([get_val(k, 'volume', 5) for k in candles])

            # --- ФИЛЬТР ЛИКВИДНОСТИ ---
            # Приблизительный оборот в USDT (Объем монеты * Цена закрытия)
            turnovers_usdt = volumes * closes
            avg_turnover = np.mean(turnovers_usdt)
            
            # Если средний оборот за свечу меньше порога - это неликвидный щиток
            if avg_turnover < self.min_turnover_usdt:
                return {"passed": False, "score": -500.0, "reason": f"low_liquidity: {avg_turnover:.0f} USDT"}

            # История (без последней свечи) и текущие значения
            hist_vol = volumes[:-1]
            hist_closes = closes[:-1]
            
            curr_open = opens[-1]
            curr_close = closes[-1]
            curr_high = highs[-1]
            curr_low = lows[-1]
            curr_vol = volumes[-1]

            # 1. Отбрасываем красные свечи
            if curr_close <= curr_open:
                return {"passed": False, "score": -100.0, "reason": "red_candle"}

            # 2. Плотность тела свечи (отсеиваем длинные тени сверху)
            candle_range = curr_high - curr_low
            body_density = (curr_close - curr_low) / candle_range if candle_range > 0 else 1.0

            if body_density < 0.5:
                return {"passed": False, "score": -50.0, "reason": "huge_upper_wick"}

            # 3. RVOL (Relative Volume)
            vol_mean = np.mean(hist_vol)
            rvol = curr_vol / vol_mean if vol_mean > 0 else 0

            # 4. Price Momentum (текущий рост в процентах)
            current_return_pct = ((curr_close - curr_open) / curr_open) * 100

            # 5. Бонус за микро-тренд
            prev_return = closes[-2] - opens[-2]
            trend_multiplier = 1.2 if prev_return > 0 else 1.0

            # Итоговый Score
            score = (rvol * current_return_pct * body_density) * trend_multiplier

            passed_strict = (rvol > self.vol_z_threshold) and (current_return_pct > self.price_z_threshold)

            return {
                "passed": passed_strict,
                "score": float(score),
                "rvol": float(rvol),
                "return_pct": float(current_return_pct),
                "body_density": float(body_density),
                "reason": "OK"
            }

        except Exception as e:
            return {"passed": False, "score": -999.0, "reason": f"error: {str(e)}"}