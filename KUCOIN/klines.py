from __future__ import annotations
from typing import List, Any
from .client import KucoinBaseClient

class KucoinKlines(KucoinBaseClient):
    async def get_klines(
        self, 
        symbol: str, 
        granularity_min: int, 
        limit: int = None,
        from_ms: int = None,
        to_ms: int = None
    ) -> List[Any]:
        params = {
            "symbol": symbol,
            "granularity": granularity_min
        }
        
        # Пробрасываем исторические периоды, если они заданы
        if from_ms is not None:
            params["from"] = from_ms
        if to_ms is not None:
            params["to"] = to_ms
            
        res = await self._request("GET", "/api/v1/kline", params=params)
        data = res.get("data", []) if isinstance(res, dict) else res
        
        # Ограничиваем выдачу, если это обычный запрос (не исторический скрапинг)
        if limit and not from_ms and not to_ms:
            data = data[:limit]
            
        return data