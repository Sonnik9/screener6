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
        logger.info(f"Сканнер инициализирован: tf={self.timeframe}, lookback={self.lookback}, алгоритм=Barcode_V2 (Дневной объем + Wicks)")

    async def aclose(self) -> None:
        await self.symbols_api.aclose()
        await self.klines_api.aclose()

    @staticmethod
    def _tf_to_minutes(tf: str) -> int:
        mapping = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "2h": 120, "4h": 240, "8h": 480, "1d": 1440}
        return mapping.get(str(tf).lower().strip(), 1)

    async def _analyze_symbol(self, symbol: str) -> Dict[str, Any]:
        try:
            # --- ШАГ 1: ПРЕДФИЛЬТР ДНЕВНОГО ОБЪЕМА (отдельный запрос) ---
            daily_candles = await self.klines_api.get_klines(
                symbol=symbol,
                granularity_min=1440, # Дневные свечи
                limit=self.cfg.filter.daily_volume_days,
            )
            
            if not daily_candles:
                return {"symbol": symbol, "passed": False, "score": -100.0, "fail_reasons": ["no_daily_data"]}

            # Считаем средний объем в USDT: Объем(монеты) * Close. В KuCoin k[2]=close, k[5]=volume
            turnovers = []
            for k in daily_candles:
                close = float(k[2] if isinstance(k, (list, tuple)) else getattr(k, 'close', 0))
                vol = float(k[5] if isinstance(k, (list, tuple)) else getattr(k, 'volume', 0))
                turnovers.append(close * vol)
            
            avg_daily_vol = sum(turnovers) / len(turnovers) if turnovers else 0
            
            if not (self.cfg.filter.daily_volume_min_usdt <= avg_daily_vol <= self.cfg.filter.daily_volume_max_usdt):
                return {
                    "symbol": symbol, "passed": False, "score": -10.0, 
                    "fail_reasons": [f"daily_vol_skip ({avg_daily_vol/1e6:.1f}M)"]
                }

            # --- ШАГ 2: ОСНОВНОЙ ТАЙМФРЕЙМ (если прошел дневной префильтр) ---
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
                "metrics": analysis.get("metrics", {}),
                "fail_reasons": [analysis["reason"]] if not analysis["passed"] else []
            }
        except Exception as e:
            return {"symbol": symbol, "passed": False, "score": -999.0, "metrics": {}, "fail_reasons": [str(e)]}

    async def scan(self) -> Dict[str, Any]:
            started_at_ms = int(time.time() * 1000)
            symbols = sorted(await self.symbols_api.get_perp_symbols(quote=self.quote, limit=self.max_symbols or None))
            sem = asyncio.Semaphore(self.concurrent_symbols)

            async def worker(sym: str) -> Dict[str, Any]:
                async with sem:
                    return await self._analyze_symbol(sym)

            logger.info(f"Запуск сканирования... Всего монет: {len(symbols)}")
            rows = await asyncio.gather(*(worker(s) for s in symbols))

            # Оставляем только те, что прошли фильтры
            valid_rows = [r for r in rows if r.get("passed", False)]
            
            # Сортируем: на 1 месте те, у которых больше всего "хороших" свечей (score = %)
            valid_rows.sort(key=lambda x: x["score"], reverse=True)
            candidates = valid_rows[:self.top_n]

            logger.info(f"Найдено подходящих монет: {len(valid_rows)}. Отбираем ТОП-{len(candidates)}.")
            if candidates:
                top_str = ", ".join([
                    f"{c['symbol']} (Prog:{c['metrics'].get('valid_wicks_pct', 0):.0f}%, "
                    f"Don:{c['metrics'].get('donchian_pct', 0):.1f}%)" 
                    for c in candidates[:5]
                ])
                logger.info(f"🔥 Лидеры: {top_str}")

            return {
                "generated_at_ms": int(time.time() * 1000),
                "scan_elapsed_ms": int(time.time() * 1000) - started_at_ms,
                "symbols_total": len(symbols),
                "symbols_passed_strict": len(valid_rows),
                "candidate_symbols": [x["symbol"] for x in candidates], 
                "candidates": candidates,
            }