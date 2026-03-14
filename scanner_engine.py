from __future__ import annotations
import asyncio
import time
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
        logger.info(f"Сканнер инициализирован: tf={self.timeframe}, lookback={self.lookback}, алгоритм=Z-Score")

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
                symbol=symbol,
                granularity_min=self._tf_to_minutes(self.timeframe),
                limit=self.lookback,
            )
            analysis = self.calc.analyze(candles)
            return {
                "symbol": symbol,
                "passed": analysis["passed"],
                "score": analysis["score"],
                "metrics": analysis,
                "fail_reasons": [analysis["reason"]] if not analysis["passed"] else []
            }
        except Exception as e:
            return {"symbol": symbol, "passed": False, "score": 0.0, "metrics": {}, "fail_reasons": [str(e)]}

    async def scan(self) -> Dict[str, Any]:
            started_at_ms = int(time.time() * 1000)
            symbols = sorted(await self.symbols_api.get_perp_symbols(quote=self.quote, limit=self.max_symbols or None))
            sem = asyncio.Semaphore(self.concurrent_symbols)

            async def worker(sym: str) -> Dict[str, Any]:
                async with sem:
                    return await self._analyze_symbol(sym)

            logger.info(f"Запуск сканирования... Всего монет: {len(symbols)}")
            rows = await asyncio.gather(*(worker(s) for s in symbols))

            # БЕРЕМ ВСЕ МОНЕТЫ СО СКОРОМ > 0 (все нормальные зеленые свечи)
            valid_rows = [r for r in rows if r.get("score", -999) > 0]
            
            # Сортируем: на 1 месте самая аномальная ракета
            valid_rows.sort(key=lambda x: x["score"], reverse=True)
            
            # Отрезаем Топ-N (например, топ 10 или 15 из конфига)
            candidates = valid_rows[:self.top_n]

            # Для логов: смотрим, сколько из них пробили "идеальный" порог
            perfect_matches = sum(1 for c in candidates if c["passed"])

            logger.info(f"Найдено растущих монет: {len(valid_rows)}. Отбираем ТОП-{len(candidates)}.")
            if candidates:
                top_3 = ", ".join([f"{c['symbol']} (Sc:{c['score']:.1f})" for c in candidates[:3]])
                logger.info(f"🔥 Лидеры сейчас: {top_3}")

            return {
                "generated_at_ms": int(time.time() * 1000),
                "scan_elapsed_ms": int(time.time() * 1000) - started_at_ms,
                "symbols_total": len(symbols),
                "symbols_passed_strict": perfect_matches,
                "candidate_symbols": [x["symbol"] for x in candidates], # Отдаем в main.py только тикеры топа
                "candidates": candidates,
            }