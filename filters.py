from __future__ import annotations
import numpy as np
from typing import List, Dict, Any

class CalculatingEngine:
    def __init__(self, filter_cfg):
        self.min_turnover_usdt = getattr(filter_cfg, 'min_turnover_usdt', 5000.0)
        # Настройки паттерна "Штрих-код"
        self.max_body_ratio = getattr(filter_cfg, 'max_body_ratio', 0.45) # Тело в среднем не больше 45% от длины свечи
        self.min_range_pct = getattr(filter_cfg, 'min_range_pct', 0.3)    # Средний размер свечи от 0.3% (чтобы было что торговать)
        self.min_crossings = getattr(filter_cfg, 'min_crossings', 15)     # Минимум 15 касаний средней оси за период
        self.max_trend_pct = getattr(filter_cfg, 'max_trend_pct', 3.0)    # Цена не должна измениться более чем на 3% от начала до конца (боковик)

    def analyze(self, candles: List[Any]) -> Dict[str, Any]:
        if not candles or len(candles) < 30:
            return {"passed": False, "score": -999.0, "reason": "not_enough_candles"}

        try:
            def get_val(k, attr, idx): return float(getattr(k, attr, k[idx] if isinstance(k, (list, tuple)) else 0))
            
            opens = np.array([get_val(k, 'open', 1) for k in candles])
            closes = np.array([get_val(k, 'close', 2) for k in candles])
            highs = np.array([get_val(k, 'high', 3) for k in candles])
            lows = np.array([get_val(k, 'low', 4) for k in candles])
            volumes = np.array([get_val(k, 'volume', 5) for k in candles])

            # --- 1. ФИЛЬТР ЛИКВИДНОСТИ ---
            turnovers_usdt = volumes * closes
            avg_turnover = np.mean(turnovers_usdt)
            if avg_turnover < self.min_turnover_usdt:
                return {"passed": False, "score": -500.0, "reason": f"low_liquidity: {avg_turnover:.0f} USDT"}

            # --- 2. ХАРАКТЕРИСТИКИ СВЕЧЕЙ (ШТРИХ-КОД) ---
            ranges = highs - lows
            ranges = np.where(ranges == 0, 1e-8, ranges) # Защита от деления на ноль
            bodies = np.abs(closes - opens)

            # Доля тела от всей свечи (меньше = длиннее тени)
            body_ratios = bodies / ranges
            avg_body_ratio = np.mean(body_ratios)

            # Средний размер свечи в % (волатильность внутри свечи)
            range_pcts = (ranges / lows) * 100
            avg_range_pct = np.mean(range_pcts)

            # --- 3. БОКОВИК И ВОЗВРАТ К СРЕДНЕМУ ---
            # Изменение цены за весь период (смотрим, нет ли сильного тренда)
            total_trend_pct = abs(closes[-1] - closes[0]) / closes[0] * 100

            # Ось "Штрих-кода" (средняя цена за окно)
            axis = np.mean(closes)
            
            # Считаем, сколько раз свечи пересекали или касались центральной оси
            # Условие: минимум свечи ниже оси, а максимум - выше оси
            touches = np.sum((lows <= axis) & (highs >= axis))

            # --- 4. ПРОВЕРКА УСЛОВИЙ ---
            passed = True
            fail_reasons = []

            if avg_body_ratio > self.max_body_ratio:
                passed = False
                fail_reasons.append(f"fat_bodies ({avg_body_ratio:.2f})")
                
            if avg_range_pct < self.min_range_pct:
                passed = False
                fail_reasons.append(f"narrow_range ({avg_range_pct:.2f}%)")
                
            if touches < self.min_crossings:
                passed = False
                fail_reasons.append(f"few_crossings ({touches})")
                
            if total_trend_pct > self.max_trend_pct:
                passed = False
                fail_reasons.append(f"trending ({total_trend_pct:.2f}%)")

            # --- 5. ОЦЕНКА (СКОРИНГ) ---
            # Идеальный штрихкод: много касаний оси, тонкие тела (большие тени), хороший размах
            # Чем больше score, тем лучше паттерн "штрихкод"
            score = (1.0 - avg_body_ratio) * avg_range_pct * touches

            if not passed:
                score = -abs(score) - 100.0 # Отрицательный скор для мусора

            return {
                "passed": passed,
                "score": float(score),
                "avg_body_ratio": float(avg_body_ratio),
                "avg_range_pct": float(avg_range_pct),
                "touches": int(touches),
                "trend_pct": float(total_trend_pct),
                "reason": "barcode_detected" if passed else ", ".join(fail_reasons)
            }

        except Exception as e:
            return {"passed": False, "score": -999.0, "reason": f"error: {str(e)}"}