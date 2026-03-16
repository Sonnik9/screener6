import asyncio
import os
from pathlib import Path
from c_log import UnifiedLogger
from config import load_config, CFG_PATH
from scanner_engine import CandidateScanner
from benchmark import run_autotune
import clicker  # Импортируем сам модуль, а не класс

logger = UnifiedLogger("main")

ROOT_DIR = Path(__file__).resolve().parent
RESULTS_FILE = ROOT_DIR / "target_links.txt"

async def run_scanner_cycle(scanner: CandidateScanner):
    res = await scanner.scan()
    candidates = res.get("candidates", [])
    
    if not candidates:
        logger.info("Цели не найдены. Сплю...")
        return

    logger.info(f"Найдено целей: {len(candidates)}")
    
    # 1. Формируем ссылки и сохраняем их в файл для кликера
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        for cand in candidates:
            # Вытягиваем тикер, даже если вернулся словарь с метриками
            sym = cand.get("symbol", cand) if isinstance(cand, dict) else cand
            
            # Адаптируем тикер под правильную ссылку KuCoin Futures (BTCUSDTM -> BTC-USDT)
            formatted_sym = sym
            if sym.endswith("USDTM"):
                formatted_sym = sym.replace("USDTM", "-USDT")
            elif sym.endswith("USDT") and "-" not in sym:
                formatted_sym = sym.replace("USDT", "-USDT")
                
            f.write(f"https://www.kucoin.com/ru/trade/{formatted_sym}\n")
            
    logger.info(f"Ссылки сохранены в файл: {RESULTS_FILE}")

    # 2. Интеграция кликера, если он включен в настройках
    if scanner.cfg.app.is_click:
        logger.info("Авто-запуск кликера...")
        # Запускаем синхронную функцию кликера в отдельном потоке, 
        # чтобы time.sleep() в кликере не заморозил весь асинхронный цикл сканера
        await asyncio.to_thread(clicker.main)

async def main():
    logger.info(f"Запуск скринера... Базовый конфиг: {CFG_PATH}")
    
    # Читаем базу, чтобы понять, нужен ли нам бенчмарк
    base_cfg = load_config(CFG_PATH)
    active_cfg_path = CFG_PATH
    
    if base_cfg.benchmark.enable:
        await run_autotune(CFG_PATH)
        if os.path.exists("bm_cfg.json"):
            active_cfg_path = "bm_cfg.json"
            logger.info(f"⚡ БЕНЧМАРК АКТИВЕН: Движок переключен на {active_cfg_path}")
    
    while True:
        try:
            # Загружаем конфиг по приоритету (база или бенчмарк)
            cfg = load_config(active_cfg_path)
            scanner = CandidateScanner(cfg)
            
            await run_scanner_cycle(scanner)
            await scanner.aclose()
            
            if cfg.app.screen_once:
                logger.info("Режим однократного сканирования. Выход.")
                break
                
            logger.info(f"Пауза {cfg.app.scan_interval_sec} сек...")
            await asyncio.sleep(cfg.app.scan_interval_sec)
            
        except Exception as e:
            logger.error(f"Ошибка в главном цикле: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем.")