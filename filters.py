from __future__ import annotations
import numpy as np
from typing import List, Dict, Any

class CalculatingEngine:
    def __init__(self, filter_cfg):
        # Пороги аномалий: насколько сильно текущий объем/цена должны превышать историческую норму
        self.vol_z_threshold = getattr(filter_cfg, 'vol_z_threshold', 2.5)
        self.price_z_threshold = getattr(filter_cfg, 'price_z_threshold', 2.0)

    def analyze(self, candles: List[Any]) -> Dict[str, Any]:
        """
        Анализ свечей с помощью Z-Score (поиск аномалий).
        """
        if not candles or len(candles) < 20:
            return {"passed": False, "score": 0.0, "reason": "not_enough_candles"}

        try:
            # Безопасное извлечение цены закрытия и объема (поддержка объектов и кортежей)
            def get_val(k, attr, idx):
                return float(getattr(k, attr, k[idx] if isinstance(k, (list, tuple)) else 0))

            closes = np.array([get_val(k, 'close', 2) for k in candles])
            volumes = np.array([get_val(k, 'volume', 5) for k in candles])

            # Историческая выборка (все свечи, кроме последней)
            hist_volumes = volumes[:-1]
            hist_closes = closes[:-1]
            
            # Текущие значения (последняя свеча)
            current_vol = volumes[-1]

            # 1. Z-Score объема
            vol_mean = np.mean(hist_volumes)
            vol_std = np.std(hist_volumes)
            if vol_std == 0:
                return {"passed": False, "score": 0.0, "reason": "zero_vol_std"}
            
            vol_z = (current_vol - vol_mean) / vol_std

            # 2. Z-Score ценового импульса (доходности)
            returns = np.diff(hist_closes) / hist_closes[:-1]
            current_return = (closes[-1] - closes[-2]) / closes[-2]
            
            ret_mean = np.mean(returns)
            ret_std = np.std(returns)
            if ret_std == 0:
                return {"passed": False, "score": 0.0, "reason": "zero_ret_std"}
                
            price_z = (current_return - ret_mean) / ret_std

            # Условие прохождения: всплеск объема + всплеск цены + свеча зеленая
            passed = (vol_z > self.vol_z_threshold) and (price_z > self.price_z_threshold) and (current_return > 0)
            
            # Итоговый скор для сортировки лучших (чем выше аномалия, тем лучше)
            score = float(vol_z + price_z) if passed else 0.0

            return {
                "passed": bool(passed),
                "score": score,
                "vol_z": float(vol_z),
                "price_z": float(price_z),
                "reason": "" if passed else f"low_z_score (V:{vol_z:.2f}, P:{price_z:.2f})"
            }

        except Exception as e:
            return {"passed": False, "score": 0.0, "reason": f"error: {str(e)}"}