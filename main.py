from __future__ import annotations
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from c_log import UnifiedLogger
from config import load_config, CFG_PATH
from scanner_engine import CandidateScanner
from clicker import main as clicker_main

logger = UnifiedLogger("main")

# Надежный абсолютный путь к файлу (создастся в папке со скриптом)
ROOT_DIR = Path(__file__).resolve().parent
RESULTS_FILE = ROOT_DIR / "target_links.txt"

async def run_scanner_cycle(cfg_path: Path):
    cfg = load_config(cfg_path)
    # Превращаем датакласс в словарь и форматируем в красивую JSON-строку
    cfg_pretty = json.dumps(asdict(cfg), indent=4, ensure_ascii=False)

    # Запись в логи (инфо)
    logger.info(f"Загружены настройки:\n{cfg_pretty}")
    # --------------------------
    scanner = CandidateScanner(cfg)
    
    logger.info("Запуск алгоритма Shtrih-Score...")
    try:
        results = await scanner.scan()
    finally:
        await scanner.aclose()
    
    candidates = results.get("candidate_symbols", [])
    
    if not candidates:
        logger.info("Цели не найдены. Сплю...")
        return

    logger.info(f"🔥 НАЙДЕНО {len(candidates)} МОНЕТ: {candidates}")

    # Сохраняем ссылки в файл
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        for sym in candidates:
            # Адаптируем тикер под правильную ссылку KuCoin (BTCUSDTM -> BTC-USDT)
            formatted_sym = sym
            if sym.endswith("USDTM"):
                formatted_sym = sym.replace("USDTM", "-USDT")
            elif sym.endswith("USDT") and "-" not in sym:
                formatted_sym = sym.replace("USDT", "-USDT")
                
            # Записываем правильную русскую ссылку!
            f.write(f"https://www.kucoin.com/ru/trade/{formatted_sym}\n")
            
    logger.info(f"Ссылки сохранены в файл: {RESULTS_FILE}. Запустите clicker.py вручную.")

async def main():
    logger.info(f"Запуск скринера... Конфиг: {CFG_PATH}")    
    
    while True:
        try:
            cfg = load_config(CFG_PATH) 
            await run_scanner_cycle(CFG_PATH)

            if cfg.app.is_click:
                clicker_main()

            if cfg.app.screen_once:
                logger.info("Режим однократного сканирования. Выход.")
                break

            logger.info(f"Ожидание {cfg.app.scan_interval_sec} сек. до следующего скана...\n{'-'*40}")
            await asyncio.sleep(cfg.app.scan_interval_sec)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Глобальная ошибка в цикле: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Теперь Ctrl+C будет срабатывать моментально
        print("\n[!] Скринер успешно остановлен пользователем (Ctrl+C).")