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
        
        # KuCoin Futures требует 'from' и 'to'
        if from_ms is not None:
            params["from"] = int(from_ms)
        if to_ms is not None:
            params["to"] = int(to_ms)
            
        # ТОЧНЫЙ ЭНДПОИНТ ИМЕННО ДЛЯ ФЬЮЧЕРСОВ
        res = await self._request("GET", "/api/v1/kline/query", params=params)
        
        data = res.get("data", []) if isinstance(res, dict) else res
        
        # Для сканера (когда нет from/to) просто режем по лимиту
        if limit and from_ms is None and to_ms is None:
            data = data[:limit]
            
        return data