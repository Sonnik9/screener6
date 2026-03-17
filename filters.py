from __future__ import annotations
import numpy as np
from typing import List, Dict, Any

class CalculatingEngine:
    def __init__(self, filter_cfg):
        self.cfg = filter_cfg

    def analyze(self, candles: List[Any]) -> Dict[str, Any]:
        required_len = max(self.cfg.barcode_pattern.window if self.cfg.barcode_pattern.enable else 10,
                           self.cfg.atr.period + 1 if self.cfg.atr.enable else 10)
                           
        if not candles or len(candles) < required_len:
            return {"passed": False, "score": -999.0, "reason": "not_enough_candles"}
            
        try:
            def get_val(k, attr, idx): return float(getattr(k, attr, k[idx] if isinstance(k, (list, tuple)) else 0))
            
            opens = np.array([get_val(k, 'open', 1) for k in candles])
            highs = np.array([get_val(k, 'high', 2) for k in candles])
            lows = np.array([get_val(k, 'low', 3) for k in candles])
            closes = np.array([get_val(k, 'close', 4) for k in candles])

            ranges = np.abs(highs - lows)

            # ==================================
            # 0. ATR
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
                
                atr_val = np.mean(true_range[-period:]) 
                current_close = closes[-1] if closes[-1] > 0 else 1e-8
                atr_pct = (atr_val / current_close) * 100.0
                passed_atr = self.cfg.atr.min_pct <= atr_pct <= self.cfg.atr.max_pct

            # ==================================
            # 1. BARCODE PATTERN v14.1
            # ==================================
            passed_barcode = True
            barcode_dist_pct = 0.0
            crosses_pct = 0.0
            high_horizont = 0.0
            low_horizont = 0.0
            crosses = 0
            
            if self.cfg.barcode_pattern.enable:
                window = self.cfg.barcode_pattern.window
                
                eval_highs = highs[-window:] if len(highs) >= window else highs
                eval_lows = lows[-window:] if len(lows) >= window else lows
                eval_closes = closes[-window:] if len(closes) >= window else closes
                
                if len(eval_lows) > 0 and eval_lows[0] > 0:
                    high_horizont = np.percentile(eval_highs, self.cfg.barcode_pattern.high_matches_pctl)
                    
                    low_pctl = 100.0 - self.cfg.barcode_pattern.low_matches_pctl
                    low_pctl = max(0.0, min(100.0, low_pctl)) 
                    low_horizont = np.percentile(eval_lows, low_pctl)
                    
                    if low_horizont > 0:
                        barcode_dist_pct = ((high_horizont - low_horizont) / low_horizont) * 100.0
                        
                        axis = (high_horizont + low_horizont) / 2.0
                        signs = np.sign(eval_closes - axis)
                        signs = signs[signs != 0] 
                        if len(signs) > 1:
                            crosses = int(np.sum(signs[:-1] != signs[1:]))
                    
                    crosses_pct = (crosses / window) * 100.0 if window > 0 else 0.0
                    
                    pass_dist = self.cfg.barcode_pattern.min_dist_pct <= barcode_dist_pct <= self.cfg.barcode_pattern.max_dist_pct
                    pass_cross = crosses_pct >= self.cfg.barcode_pattern.min_crosses_pct
                    passed_barcode = pass_dist and pass_cross
                else:
                    passed_barcode = False

            # ==================================
            # 2. NARROW PENALTY (Штраф за мелкие свечи)
            # ==================================
            passed_penalty = True
            penalty_pct = 0.0
            
            if hasattr(self.cfg, 'narrow_penalty') and self.cfg.narrow_penalty.enable:
                lows_safe = np.where(lows > 0, lows, 1e-8)
                candles_pct = (ranges / lows_safe) * 100.0
                
                narrow_count = int(np.sum(candles_pct < self.cfg.narrow_penalty.min_range_pct))
                if len(candles_pct) > 0:
                    penalty_pct = (narrow_count / len(candles_pct)) * 100.0
                    passed_penalty = penalty_pct <= self.cfg.narrow_penalty.max_penalty_pct

            is_strict_pass = passed_barcode and passed_atr and passed_penalty
            
            # ==================================
            # РАСЧЕТ ИНДЕКСА ЛОЯЛЬНОСТИ v14.1
            # ==================================
            safe_div = lambda a, b: float(a) / float(b) if b > 0 else 0.0
            
            a_score = safe_div(atr_pct, self.cfg.atr.min_pct) * 100
            
            if barcode_dist_pct >= self.cfg.barcode_pattern.min_dist_pct:
                b_score = safe_div(self.cfg.barcode_pattern.min_dist_pct, barcode_dist_pct) * 100
            else:
                b_score = safe_div(barcode_dist_pct, self.cfg.barcode_pattern.min_dist_pct) * 100
            
            c_score = safe_div(crosses_pct, self.cfg.barcode_pattern.min_crosses_pct) * 100
            
            a_score = min(a_score, 200)
            b_score = min(b_score, 200)
            c_score = min(c_score, 200)

            approx_score = (a_score + b_score + (c_score * 2.0)) / 4.0

            return {
                "passed": is_strict_pass,
                "score": float(approx_score),
                "metrics": {
                    "approx_score": float(approx_score),
                    "barcode_dist_pct": float(barcode_dist_pct),
                    "atr_pct": float(atr_pct),
                    "high_horizont": float(high_horizont),
                    "low_horizont": float(low_horizont),
                    "crosses": crosses,
                    "crosses_pct": float(crosses_pct),
                    "penalty_pct": float(penalty_pct)
                },
                "reason": "strict_match" if is_strict_pass else "near_match"
            }
        except Exception as e:
            return {"passed": False, "score": -999.0, "reason": f"calc_error: {str(e)}"}