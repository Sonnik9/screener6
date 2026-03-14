from __future__ import annotations
import asyncio
import time
import aiohttp
from typing import Any, Dict
from config import AppConfig
from filters import CalculatingEngine
from KUCOIN.klines import KucoinKlines
from KUCOIN.symbol import KucoinSymbols
from c_log import UnifiedLogger

logger = UnifiedLogger("scanner_engine")

class CandidateScanner:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.timeframe = self.cfg.filter.timeframe
        self.lookback = int(self.cfg.filter.lookback_candles)
        self.quote = self.cfg.app.quote
        self.max_symbols = int(getattr(self.cfg.app, "max_symbols", 0) or 0)
        self.concurrent_symbols = int(self.cfg.app.concurrent_symbols)
        self.top_n = int(self.cfg.app.top_n)

        self.symbols_api = KucoinSymbols()
        self.klines_api = KucoinKlines(
            request_interval_sec=max(0.05, float(self.cfg.app.request_interval_ms) / 1000.0),
            rate_limit_backoff_sec=2.0,
        )
        self.calc = CalculatingEngine(self.cfg.filter)
        logger.info(f"Сканнер: tf={self.timeframe}, lookback={self.lookback}, алгоритм=Strict_Barcode (Real USDT Vol)")

    async def aclose(self) -> None:
        await self.symbols_api.aclose()
        await self.klines_api.aclose()

    @staticmethod
    def _tf_to_minutes(tf: str) -> int:
        mapping = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "2h": 120, "4h": 240, "8h": 480, "1d": 1440}
        return mapping.get(str(tf).lower().strip(), 1)

    async def _analyze_symbol(self, symbol: str) -> Dict[str, Any]:
        try:
            candles = await self.klines_api.get_klines(
                symbol=symbol, granularity_min=self._tf_to_minutes(self.timeframe), limit=self.lookback
            )
            analysis = self.calc.analyze(candles)
            return {
                "symbol": symbol,
                "passed": analysis["passed"],
                "score": analysis["score"],
                "metrics": analysis.get("metrics", {}),
                "fail_reasons": [analysis["reason"]] if not analysis["passed"] else []
            }
        except Exception as e:
            return {"symbol": symbol, "passed": False, "score": -999.0, "metrics": {}, "fail_reasons": [str(e)]}

    async def scan(self) -> Dict[str, Any]:
            started_at_ms = int(time.time() * 1000)
            
            all_symbols = sorted(await self.symbols_api.get_perp_symbols(quote=self.quote, limit=self.max_symbols or None))
            
            logger.info(f"Символов: {len(all_symbols)}. Запуск сканирования (истинный фильтр объема по свечам)...")

            sem = asyncio.Semaphore(self.concurrent_symbols)
            async def worker(sym: str) -> Dict[str, Any]:
                async with sem:
                    return await self._analyze_symbol(sym)

            rows = await asyncio.gather(*(worker(s) for s in all_symbols))

            # Берем только те, что СТРОГО прошли ВСЕ проверки
            valid_rows = [r for r in rows if r.get("passed", False)]
            valid_rows.sort(key=lambda x: x["score"], reverse=True)
            candidates = valid_rows[:self.top_n]

            if candidates:
                top_str = ", ".join([
                    f"{c['symbol']} (Sc:{c['score']:.0f}, Vol:{c['metrics'].get('daily_vol_est', 0)/1e6:.1f}M, "
                    f"Don:{c['metrics'].get('donchian_pct', 0):.1f}%)" 
                    for c in candidates[:5]
                ])
                logger.info(f"🔥 Лидеры: {top_str}")

            return {
                "generated_at_ms": int(time.time() * 1000),
                "scan_elapsed_ms": int(time.time() * 1000) - started_at_ms,
                "symbols_total": len(all_symbols),
                "symbols_passed_strict": len(valid_rows),
                "candidate_symbols": [x["symbol"] for x in candidates], 
                "candidates": candidates,
            }

# class CandidateScanner:
#     def __init__(self, cfg: AppConfig):
#         self.cfg = cfg
#         self.timeframe = self.cfg.filter.timeframe
#         self.lookback = int(self.cfg.filter.lookback_candles)
#         self.quote = self.cfg.app.quote
#         self.max_symbols = int(getattr(self.cfg.app, "max_symbols", 0) or 0)
#         self.concurrent_symbols = int(self.cfg.app.concurrent_symbols)
#         self.top_n = int(self.cfg.app.top_n)

#         self.symbols_api = KucoinSymbols()
#         self.klines_api = KucoinKlines(
#             request_interval_sec=max(0.05, float(self.cfg.app.request_interval_ms) / 1000.0),
#             rate_limit_backoff_sec=2.0,
#         )
#         self.calc = CalculatingEngine(self.cfg.filter)
#         logger.info(f"Сканнер: tf={self.timeframe}, lookback={self.lookback}, алгоритм=Barcode_V3 (Fast Ticker)")

#     async def aclose(self) -> None:
#         await self.symbols_api.aclose()
#         await self.klines_api.aclose()

#     @staticmethod
#     def _tf_to_minutes(tf: str) -> int:
#         mapping = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "2h": 120, "4h": 240, "8h": 480, "1d": 1440}
#         return mapping.get(str(tf).lower().strip(), 1)

#     async def _get_24h_turnovers(self) -> Dict[str, float]:
#         """Получаем 24h Turnover (USDT) по всем фьючерсам за 1 быстрый запрос"""
#         try:
#             async with aiohttp.ClientSession() as session:
#                 async with session.get("https://api-futures.kucoin.com/api/v1/contracts/active") as resp:
#                     data = await resp.json()
#                     turnovers = {}
#                     for item in data.get("data", []):
#                         turnovers[item["symbol"]] = float(item.get("turnoverOf24h", 0))
#                     return turnovers
#         except Exception as e:
#             logger.error(f"Ошибка получения 24h объемов: {e}")
#             return {}

#     async def _analyze_symbol(self, symbol: str, vol_24h: float) -> Dict[str, Any]:
#         try:
#             candles = await self.klines_api.get_klines(
#                 symbol=symbol, granularity_min=self._tf_to_minutes(self.timeframe), limit=self.lookback
#             )
#             analysis = self.calc.analyze(candles)
#             return {
#                 "symbol": symbol,
#                 "passed": analysis["passed"],
#                 "score": analysis["score"],
#                 "metrics": {**analysis.get("metrics", {}), "vol_24h_m": vol_24h / 1e6},
#                 "fail_reasons": [analysis["reason"]] if not analysis["passed"] else []
#             }
#         except Exception as e:
#             return {"symbol": symbol, "passed": False, "score": -999.0, "metrics": {}, "fail_reasons": [str(e)]}
            
#     async def scan(self) -> Dict[str, Any]:
#                 started_at_ms = int(time.time() * 1000)
                
#                 all_symbols = sorted(await self.symbols_api.get_perp_symbols(quote=self.quote, limit=self.max_symbols or None))
#                 turnovers_24h = await self._get_24h_turnovers()
                
#                 valid_symbols = []
#                 for sym in all_symbols:
#                     vol = turnovers_24h.get(sym, 0)
#                     if self.cfg.filter.daily_volume_min_usdt <= vol <= self.cfg.filter.daily_volume_max_usdt:
#                         valid_symbols.append((sym, vol))

#                 logger.info(f"Символов: {len(all_symbols)} -> После фильтра объема: {len(valid_symbols)}. Сканируем...")

#                 sem = asyncio.Semaphore(self.concurrent_symbols)
#                 async def worker(sym_data) -> Dict[str, Any]:
#                     sym, vol = sym_data
#                     async with sem:
#                         return await self._analyze_symbol(sym, vol)

#                 rows = await asyncio.gather(*(worker(s) for s in valid_symbols))

#                 valid_rows = [r for r in rows if r.get("score", -999) > 0]
#                 valid_rows.sort(key=lambda x: x["score"], reverse=True)
#                 candidates = valid_rows[:self.top_n]
#                 perfect_matches = len([r for r in valid_rows if r.get("passed", False)])

#                 if candidates:
#                     top_str = ", ".join([
#                         f"{c['symbol']} (Sc:{c['score']:.0f}, Vol:{c['metrics'].get('vol_24h_m', 0):.1f}M, "
#                         f"Don:{c['metrics'].get('donchian_pct', 0):.1f}%, Trend:{c['metrics'].get('trend_pct', 0):.1f}%)" 
#                         for c in candidates[:5]
#                     ])
#                     logger.info(f"🔥 Лидеры: {top_str}")

#                 return {
#                     "generated_at_ms": int(time.time() * 1000),
#                     "scan_elapsed_ms": int(time.time() * 1000) - started_at_ms,
#                     "symbols_total": len(all_symbols),
#                     "symbols_passed_strict": perfect_matches,
#                     "candidate_symbols": [x["symbol"] for x in candidates], 
#                     "candidates": candidates,
#                 }