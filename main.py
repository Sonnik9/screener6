from __future__ import annotations
import asyncio
import os
import subprocess
from pathlib import Path
from c_log import UnifiedLogger
from config import load_config, CFG_PATH
from scanner_engine import CandidateScanner

logger = UnifiedLogger("main")

RESULTS_FILE = "target_links.txt"
CLICKER_SCRIPT = "clicker.py"  # <-- УБЕДИТЕСЬ, ЧТО ИМЯ ФАЙЛА ВЕРНОЕ

async def run_scanner_and_clicker(cfg_path: Path):
    cfg = load_config(cfg_path)
    scanner = CandidateScanner(cfg)
    
    logger.info("Запуск алгоритма Z-Score...")
    try:
        results = await scanner.scan()
    finally:
        await scanner.aclose()
    
    candidates = results.get("candidate_symbols", [])
    logger.info(f"Сканирование завершено. Найдено подходящих монет: {len(candidates)}")
    
    if not candidates:
        logger.info("Цели не найдены. Ожидание следующего цикла.")
        return

    # Сохраняем ссылки для KuCoin
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        for sym in candidates:
            # Для фьючерсов ссылка может быть https://www.kucoin.com/futures/trade/...
            # По умолчанию генерируем стандартную торговую ссылку
            f.write(f"https://www.kucoin.com/trade/{sym}\n")
    
    logger.info(f"Ссылки сохранены в файл: {RESULTS_FILE}")

    # Запускаем кликер
    if os.path.exists(CLICKER_SCRIPT):
        logger.info(f"Запуск автоматизации: {CLICKER_SCRIPT}")
        try:
            # Запуск скрипта в фоне, чтобы не блокировать основной поток
            subprocess.Popen(["python", CLICKER_SCRIPT])
        except Exception as e:
            logger.error(f"Ошибка вызова кликера: {e}")
    else:
        logger.warning(f"Скрипт {CLICKER_SCRIPT} не найден! Кликер не запущен.")

async def main():
    logger.info(f"main start cfg={CFG_PATH}")
    await run_scanner_and_clicker(CFG_PATH)
    logger.info("main finished")

if __name__ == "__main__":
    asyncio.run(main())