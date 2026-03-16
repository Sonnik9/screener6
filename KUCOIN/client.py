import asyncio
import time
import aiohttp
from typing import Optional, Dict, Any
from c_log import UnifiedLogger

logger = UnifiedLogger("kucoin_client")

class KucoinBaseClient:
    def __init__(self, request_interval_sec: float = 0.1, rate_limit_backoff_sec: float = 2.0):
        self.base_url = "https://api-futures.kucoin.com"
        self.request_interval_sec = request_interval_sec
        self.rate_limit_backoff_sec = rate_limit_backoff_sec
        
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()

    async def _init_session(self):
        if self.session is None or self.session.closed:
            # Отключаем строгий SSL для обхода отвалов DNS Кукоина
            connector = aiohttp.TCPConnector(ssl=False)
            self.session = aiohttp.ClientSession(connector=connector)

    async def aclose(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _wait_rate_limit(self):
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self.request_interval_sec:
                await asyncio.sleep(self.request_interval_sec - elapsed)
            self._last_request_time = time.time()

    async def _request(self, method: str, endpoint: str, params: Dict[str, Any] = None, retry: int = 4) -> Any:
        await self._init_session()
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(retry):
            await self._wait_rate_limit()
            try:
                async with self.session.request(method, url, params=params, timeout=10) as resp:
                    if resp.status == 429:
                        logger.warning(f"KuCoin 429 Rate Limit. Ждем {self.rate_limit_backoff_sec} сек...")
                        await asyncio.sleep(self.rate_limit_backoff_sec)
                        continue
                        
                    resp.raise_for_status()
                    data = await resp.json()
                    
                    if str(data.get("code", "200000")) != "200000":
                        raise Exception(f"KuCoin API error: {data}")
                        
                    return data
            except Exception as e:
                if attempt == retry - 1:
                    logger.error(f"API отвал после {retry} попыток: {endpoint} | Ошибка: {e}")
                    raise
                await asyncio.sleep(1.0)