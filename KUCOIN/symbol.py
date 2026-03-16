from __future__ import annotations
from typing import List, Dict, Any
from .client import KucoinBaseClient

class KucoinSymbols(KucoinBaseClient):
    async def get_perp_symbols(self, quote: str = "USDT", limit: int = None) -> List[str]:
        res = await self._request("GET", "/api/v1/contracts/active")
        data = res.get("data", [])
        symbols = [
            item["symbol"] for item in data 
            if item.get("quoteCurrency") == quote and item.get("status") == "Open"
        ]
        return symbols[:limit] if limit else symbols

    async def get_24h_turnovers(self, quote: str = "USDT") -> Dict[str, float]:
        """Получает объемы 24h в USDT для всех активных контрактов"""
        res = await self._request("GET", "/api/v1/contracts/active")
        data = res.get("data", [])
        turnovers = {}
        for item in data:
            if item.get("quoteCurrency") == quote and item.get("status") == "Open":
                turnovers[item["symbol"]] = float(item.get("turnoverOf24h", 0.0))
        return turnovers