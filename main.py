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
    near_candidates = res.get("near_candidates", [])
    
    logger.info(f"Найдено строгих целей: {len(candidates)}. Ближайших приближений: {len(near_candidates)}")

    # 1. СТРОГИЕ ЦЕЛИ (Идеальный паттерн)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        for cand in candidates:
            sym = cand.get("symbol", cand) if isinstance(cand, dict) else cand
            formatted_sym = sym.replace("USDT", "USDTM") if sym.endswith("USDT") else sym
            f.write(f"https://www.kucoin.com/ru/trade/futures/{formatted_sym}\n")
            
    if candidates:
        logger.info(f"✅ Строгие ссылки сохранены в файл: {RESULTS_FILE}")

    # 2. ПРИБЛИЖЕННЫЕ ЦЕЛИ (Аппроксимация)
    NEAR_FILE = ROOT_DIR / "near_links.txt"
    if near_candidates:
        with open(NEAR_FILE, "w", encoding="utf-8") as f:
            f.write("=== ТОП МОНЕТ ПО ИНДЕКСУ ЛОЯЛЬНОСТИ К КОНФИГУ ===\n\n")
            for i, cand in enumerate(near_candidates, 1):
                sym = cand.get("symbol", cand) if isinstance(cand, dict) else cand
                formatted_sym = sym.replace("USDT", "USDTM") if sym.endswith("USDT") else sym
                m = cand.get("metrics", {})
                score = cand.get("score", 0)
                
                f.write(f"#{i} {sym} | Индекс: {score:.1f}%\n")
                f.write(f"Ссылка: https://www.kucoin.com/ru/trade/futures/{formatted_sym}\n")
                f.write(f"ATR: {m.get('atr_pct',0):.2f}% | Donchian: {m.get('donchian_pct',0):.2f}% | Drift: {m.get('drift_pct',0):.2f}%\n")
                f.write(f"Мясорубка: {m.get('compression',0):.2f} | Wicks Progress: {m.get('wicks_progress_pct',0):.1f}%\n")
                f.write("-" * 50 + "\n")
                
        logger.info(f"🔍 Ближайшие кандидаты с метриками выгружены в: {NEAR_FILE}")

    # 3. Интеграция кликера (кликает ТОЛЬКО по строгим!)
    if scanner.cfg.app.is_click and candidates:
        logger.info("Авто-запуск кликера для строгих целей...")
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