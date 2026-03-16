import asyncio
import os
from c_log import UnifiedLogger
from config import load_config, CFG_PATH
from scanner_engine import CandidateScanner
from benchmark import run_autotune
from clicker import Clicker

logger = UnifiedLogger("main")

async def run_scanner_cycle(scanner: CandidateScanner):
    res = await scanner.scan()
    if not res.get("candidates"):
        logger.info("Цели не найдены. Сплю...")
    else:
        logger.info(f"Найдено целей: {len(res['candidates'])}")
        
        # Интеграция кликера, если он включен
        if scanner.cfg.app.is_click:
            clicker = Clicker()
            await clicker.process_candidates(res['candidates'])

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
            # Загружаем конфиг по приоритету
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