from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import aiohttp


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class Kline:
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float = 0.0


class KucoinKlines:
    """KuCoin Futures klines via REST.

    Base endpoint:
        GET /api/v1/kline/query?symbol={symbol}&granularity={minutes}

    For ranged history, KuCoin docs/examples currently show `from`/`to` query
    parameters on the same endpoint. Older integrations also reference
    `startAt`/`endAt`, and some docs mention seconds for the start time. To stay
    robust, `get_klines_range()` tries several query variants and normalizes the
    response timestamps to milliseconds.
    """

    def __init__(
        self,
        base_url: str = "https://api-futures.kucoin.com",
        timeout_sec: float = 20.0,
        retries: int = 3,
        request_interval_sec: float = 0.18,
        rate_limit_backoff_sec: float = 2.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=float(timeout_sec))
        self.retries = int(retries)

        self.request_interval_sec = float(request_interval_sec)
        self.rate_limit_backoff_sec = float(rate_limit_backoff_sec)

        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

        self._req_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._backoff_until = 0.0
        self._cache: Dict[Tuple[str, int, int], List[Kline]] = {}
        self._range_cache: Dict[Tuple[str, int, int, int], List[Kline]] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session
        async with self._session_lock:
            if self._session is not None and not self._session.closed:
                return self._session
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300, enable_cleanup_closed=True)
            self._session = aiohttp.ClientSession(timeout=self.timeout, connector=connector)
            return self._session

    async def aclose(self) -> None:
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
        self._session = None

    async def _respect_rate_limit(self) -> None:
        async with self._req_lock:
            now = time.monotonic()

            if self._backoff_until > now:
                await asyncio.sleep(self._backoff_until - now)
                now = time.monotonic()

            delta = now - self._last_request_at
            if delta < self.request_interval_sec:
                await asyncio.sleep(self.request_interval_sec - delta)

            self._last_request_at = time.monotonic()

    async def _get_json(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_err: Optional[Exception] = None

        for attempt in range(1, self.retries + 1):
            try:
                await self._respect_rate_limit()

                session = await self._get_session()
                async with session.get(url) as resp:
                    text = await resp.text()

                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        try:
                            backoff = float(retry_after) if retry_after else (self.rate_limit_backoff_sec * attempt)
                        except Exception:
                            backoff = self.rate_limit_backoff_sec * attempt

                        async with self._req_lock:
                            self._backoff_until = max(self._backoff_until, time.monotonic() + backoff)

                        raise RuntimeError("RATE_LIMIT_429")

                    if resp.status != 200:
                        raise RuntimeError(f"HTTP {resp.status}: {text}")

                    data = await resp.json()
                    if not isinstance(data, dict):
                        raise RuntimeError(f"Bad JSON root: {type(data)}")
                    return data

            except Exception as e:
                last_err = e
                s = (str(e) or "").lower()

                if "session is closed" in s or "connector is closed" in s or "clientconnectorerror" in s:
                    self._session = None

                if "rate_limit_429" in s:
                    await asyncio.sleep(self.rate_limit_backoff_sec * attempt)
                elif attempt < self.retries:
                    await asyncio.sleep(0.35 * attempt)

                if attempt >= self.retries:
                    break

        raise RuntimeError(f"KuCoin REST failed: {path} err={last_err}")

    @staticmethod
    def _to_float(v: Any, default: float = 0.0) -> float:
        try:
            return float(v)
        except Exception:
            return default

    @staticmethod
    def _to_int(v: Any, default: int = 0) -> int:
        try:
            return int(v)
        except Exception:
            return default

    def _parse_rows(self, rows: Any) -> List[Kline]:
        if not isinstance(rows, list):
            return []

        out: List[Kline] = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            ts_raw = self._to_int(row[0], 0)
            # KuCoin can return seconds or milliseconds depending on product/docs.
            ts_ms = ts_raw * 1000 if ts_raw and ts_raw < 10_000_000_000 else ts_raw
            out.append(
                Kline(
                    ts_ms=ts_ms or _now_ms(),
                    open=self._to_float(row[1]),
                    high=self._to_float(row[2]),
                    low=self._to_float(row[3]),
                    close=self._to_float(row[4]),
                    volume=self._to_float(row[5]),
                    turnover=self._to_float(row[6]) if len(row) > 6 else 0.0,
                )
            )

        out.sort(key=lambda x: x.ts_ms)
        return out

    def _build_query_path(
        self,
        *,
        symbol: str,
        granularity_min: int,
        start_value: int,
        end_value: int,
        use_from_to: bool,
    ) -> str:
        params = {
            "symbol": str(symbol).upper().strip(),
            "granularity": int(granularity_min),
        }
        if use_from_to:
            params["from"] = int(start_value)
            params["to"] = int(end_value)
        else:
            params["startAt"] = int(start_value)
            params["endAt"] = int(end_value)
        return f"/api/v1/kline/query?{urlencode(params)}"

    def _candidate_range_paths(self, symbol: str, granularity_min: int, start_at_ms: int, end_at_ms: int) -> List[str]:
        s_ms = int(start_at_ms)
        e_ms = int(end_at_ms)
        s_sec = max(0, s_ms // 1000)
        e_sec = max(0, e_ms // 1000)
        paths: List[str] = []
        seen = set()
        variants = [
            (s_ms, e_ms, True),
            (s_ms, e_ms, False),
            (s_sec, e_sec, True),
            (s_sec, e_sec, False),
        ]
        for start_value, end_value, use_from_to in variants:
            path = self._build_query_path(
                symbol=symbol,
                granularity_min=granularity_min,
                start_value=start_value,
                end_value=end_value,
                use_from_to=use_from_to,
            )
            if path not in seen:
                seen.add(path)
                paths.append(path)
        return paths

    async def get_klines(
        self,
        symbol: str,
        granularity_min: int = 1,
        limit: int = 60,
    ) -> List[Kline]:
        sym = str(symbol).upper().strip()
        gran = int(granularity_min)
        if gran <= 0:
            raise ValueError("granularity_min must be > 0")
        if limit <= 0:
            return []

        cache_key = (sym, gran, int(limit))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return list(cached)

        path = f"/api/v1/kline/query?symbol={sym}&granularity={gran}"
        js = await self._get_json(path)
        rows = js.get("data") or []
        out = self._parse_rows(rows)
        if len(out) > limit:
            out = out[-int(limit):]
        self._cache[cache_key] = list(out)
        return out

    async def get_klines_range(
        self,
        symbol: str,
        granularity_min: int,
        start_at_ms: int,
        end_at_ms: int,
        max_rows_per_query: int = 1400,
    ) -> List[Kline]:
        sym = str(symbol).upper().strip()
        gran = int(granularity_min)
        start_ms = int(start_at_ms)
        end_ms = int(end_at_ms)
        if gran <= 0:
            raise ValueError("granularity_min must be > 0")
        if end_ms < start_ms:
            return []

        cache_key = (sym, gran, start_ms, end_ms)
        cached = self._range_cache.get(cache_key)
        if cached is not None:
            return list(cached)

        step_ms = gran * 60 * 1000
        chunk_span_ms = max(step_ms, step_ms * max(1, int(max_rows_per_query) - 1))
        merged: Dict[int, Kline] = {}

        cur_start = start_ms
        while cur_start <= end_ms:
            cur_end = min(end_ms, cur_start + chunk_span_ms)
            rows_for_chunk: List[Kline] = []
            last_err: Exception | None = None

            for path in self._candidate_range_paths(sym, gran, cur_start, cur_end):
                try:
                    js = await self._get_json(path)
                    rows = js.get("data") or []
                    rows_for_chunk = self._parse_rows(rows)
                    if rows_for_chunk:
                        break
                except Exception as e:
                    last_err = e
                    continue

            if last_err is not None and not rows_for_chunk:
                raise RuntimeError(f"KuCoin kline range fetch failed for {sym}: {last_err}")

            for item in rows_for_chunk:
                if start_ms <= int(item.ts_ms) <= end_ms:
                    merged[int(item.ts_ms)] = item

            if cur_end >= end_ms:
                break
            cur_start = cur_end + step_ms

        out = [merged[ts] for ts in sorted(merged)]
        self._range_cache[cache_key] = list(out)
        return out


# ----------------------------
# SELF TEST
# ----------------------------
async def _main():
    api = KucoinKlines()
    rows = await api.get_klines("XBTUSDTM", 1, 10)
    print(f"KUCOIN klines: {len(rows)}")
    for r in rows[-3:]:
        print(r)
    await api.aclose()


if __name__ == "__main__":
    asyncio.run(_main())
