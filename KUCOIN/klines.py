from typing import List, Any
from KUCOIN.client import KucoinBaseClient

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
        
        if from_ms is not None:
            params["from"] = from_ms
        if to_ms is not None:
            params["to"] = to_ms
            
        # ИСПРАВЛЕННЫЙ ЭНДПОИНТ: /api/v1/kline/query (для фьючерсов)
        res = await self._request("GET", "/api/v1/kline/query", params=params)
        data = res.get("data", []) if isinstance(res, dict) else res
        
        if limit and not from_ms and not to_ms:
            data = data[:limit]
            
        return data