import asyncio
import os
from pathlib import Path
from typing import Dict, Any

from c_log import UnifiedLogger
from config import load_config, CFG_PATH, AppConfig
from scanner_engine import CandidateScanner
from benchmark import run_autotune
import clicker
from tg_sender import TelegramSender

logger = UnifiedLogger("main")

ROOT_DIR = Path(__file__).resolve().parent
RESULTS_FILE = ROOT_DIR / "target_links.txt"
NEAR_FILE = ROOT_DIR / "near_links.txt"

# ==========================================
# HELPER: Шаблонизатор и форматтер вывода
# ==========================================
class ResultFormatter:
    @staticmethod
    def get_kucoin_url(symbol: str) -> str:
        """Нормализует тикер и генерирует прямую ссылку на фьючерсы KuCoin."""
        formatted_sym = symbol.replace("USDT", "USDTM") if symbol.endswith("USDT") else symbol
        return f"https://www.kucoin.com/ru/trade/futures/{formatted_sym}"

    @staticmethod
    def extract_symbol(coin_data: Any) -> str:
        return coin_data.get("symbol", coin_data) if isinstance(coin_data, dict) else str(coin_data)

    @staticmethod
    def build_text_block(idx: int, sym: str, score: float, metrics: Dict[str, Any]) -> str:
        """Универсальный текстовый шаблон (для консоли и лог-файла)."""
        link = ResultFormatter.get_kucoin_url(sym)
        return (
            f"#{idx} {sym} | Индекс: {score:.1f}%\n"
            f"Ссылка: {link}\n"
            f"ATR: {metrics.get('atr_pct', 0):.2f}% | Штрих-Дистанция: {metrics.get('barcode_dist_pct', 0):.2f}%\n"
            f"Ось: {metrics.get('low_horizont', 0):.5g} - {metrics.get('high_horizont', 0):.5g} | "
            f"Пересечений оси: {metrics.get('crosses', 0)} ({metrics.get('crosses_pct', 0):.1f}%)\n"
            f"{'-' * 50}"
        )

    @staticmethod
    def build_tg_block(idx: int, sym: str, score: float, metrics: Dict[str, Any]) -> str:
        """HTML-шаблон для Telegram."""
        link = ResultFormatter.get_kucoin_url(sym)
        return (
            f"<b>#{idx} {sym}</b> | Индекс: {score:.1f}%\n"
            f"📏 Коридор: <code>{metrics.get('low_horizont', 0):.5g}</code> - <code>{metrics.get('high_horizont', 0):.5g}</code>\n"
            f"📈 ATR: {metrics.get('atr_pct', 0):.2f}% | Дистанция: {metrics.get('barcode_dist_pct', 0):.2f}%\n"
            f"⚡ Пересечений: {metrics.get('crosses', 0)} ({metrics.get('crosses_pct', 0):.1f}%)\n"
            f"🔗 <a href='{link}'>Открыть график</a>\n"
            f"〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️"
        )

    @staticmethod
    def build_startup_message(cfg: AppConfig, config_source: str) -> str:
        """Собирает аннотированную сводку настроек для пуша при старте."""
        f = cfg.filter
        a = cfg.app
        
        msg = (
            f"🚀 <b>Скринер запущен (v16)</b>\n"
            f"📁 Конфиг: <code>{config_source}</code>\n\n"
            f"<b>⚙️ Базовые настройки:</b>\n"
            f"🔸 Пара: <b>{a.quote}</b> | ТФ: <b>{f.timeframe}</b>\n"
            f"🔸 Окно анализа: <b>{f.lookback_candles}</b> свечей\n"
            f"🔸 Пауза между сканами: <b>{a.scan_interval_sec}</b> сек\n\n"
            f"<b>📊 Активные фильтры:</b>\n"
        )
        
        if f.daily_volume.enable:
            msg += f"🔹 <b>Объем (24ч):</b> {f.daily_volume.min_usdt:,.0f} - {f.daily_volume.max_usdt:,.0f} $\n"
        if f.atr.enable:
            msg += f"🔹 <b>ATR ({f.atr.period}):</b> {f.atr.min_pct}% - {f.atr.max_pct}%\n"
        if f.barcode_pattern.enable:
            msg += (f"🔹 <b>Штрихкод (окно {f.barcode_pattern.window}):</b>\n"
                    f"   ├ Коридор: {f.barcode_pattern.min_dist_pct}% - {f.barcode_pattern.max_dist_pct}%\n"
                    f"   └ Пересечений оси: &gt;= {f.barcode_pattern.min_crosses_pct}%\n")  # Изменено на &gt;=
        if hasattr(f, 'narrow_penalty') and f.narrow_penalty.enable:
            msg += f"🔹 <b>Штраф дожи:</b> свечи &lt; {f.narrow_penalty.min_range_pct}% (допуск {f.narrow_penalty.max_penalty_pct}% шт)\n"  # Изменено на &lt;
        if f.approximation.enable:
            msg += f"🔹 <b>Аппроксимация:</b> проход от {f.approximation.min_score_pct}% (ТОП-{cfg.app.top_n})\n"
            
        return msg


# ==========================================
# MAIN CORE: Бизнес-логика сканера
# ==========================================
async def run_scanner_cycle(scanner: CandidateScanner, cfg: AppConfig, tg_bot: TelegramSender | None):
    res = await scanner.scan()
    candidates = res.get("candidates", [])
    near_candidates = res.get("near_candidates", [])
    
    logger.info(f"Найдено строгих целей: {len(candidates)}. Ближайших приближений: {len(near_candidates)}")

    # 1. СТРОГИЕ ЦЕЛИ (Идеальный паттерн)
    if candidates:
        strict_tg_lines = ["<b>🎯 СТРОГИЕ ЦЕЛЕВЫЕ МОНЕТЫ 🎯</b>\n"]
        print("\n=== 🎯 СТРОГИЕ ЦЕЛЕВЫЕ МОНЕТЫ 🎯 ===")
        
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            for cand in candidates:
                sym = ResultFormatter.extract_symbol(cand)
                link = ResultFormatter.get_kucoin_url(sym)
                f.write(f"{link}\n")
                
                print(f"✅ {sym} | {link}")
                strict_tg_lines.append(f"✅ <b>{sym}</b>\n🔗 <a href='{link}'>Открыть график</a>\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️")
                
        logger.info(f"✅ Строгие ссылки сохранены в файл: {RESULTS_FILE}")

        # Пушим целевые монеты в ТГ
        if tg_bot and cfg.telegram.enable:
            await tg_bot.send_message("\n".join(strict_tg_lines))

        # Интеграция кликера (кликает ТОЛЬКО по строгим!)
        if cfg.app.is_click:
            logger.info("Авто-запуск кликера для строгих целей...")
            await asyncio.to_thread(clicker.main)

    # 2. ПРИБЛИЖЕННЫЕ ЦЕЛИ (Консоль + Файл + Telegram)
    if near_candidates:
        top_coins = near_candidates[:cfg.app.top_n]
        
        # Инициализация буферов вывода с явными пометками
        file_lines = ["=== 🔍 ПРИБЛИЖЕННЫЕ МОНЕТЫ (ТОП ПО ИНДЕКСУ v16) ===\n"]
        tg_lines = ["<b>🔍 ПРИБЛИЖЕННЫЕ МОНЕТЫ (v16) 🔍</b>\n"]
        
        print(f"\n{file_lines[0].strip()}")
        
        for idx, coin in enumerate(top_coins, 1):
            sym = ResultFormatter.extract_symbol(coin)
            score = coin.get("score", 0)
            metrics = coin.get("metrics", {})
            
            # Генерация блоков через хелпер
            text_block = ResultFormatter.build_text_block(idx, sym, score, metrics)
            tg_block = ResultFormatter.build_tg_block(idx, sym, score, metrics)
            
            # Наполнение буферов и консоли
            print(text_block)
            file_lines.append(text_block)
            tg_lines.append(tg_block)
            
        # Запись в файл
        with open(NEAR_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(file_lines))
        logger.info(f"🔍 Ближайшие кандидаты v16 выгружены в: {NEAR_FILE}")
        
        # Отправка в Telegram
        if tg_bot and cfg.telegram.enable:
            await tg_bot.send_message("\n".join(tg_lines))


# ==========================================
# ENTRY POINT
# ==========================================
async def main():
    logger.info(f"Запуск скринера... Базовый конфиг: {CFG_PATH}")
    
    base_cfg = load_config(CFG_PATH)
    active_cfg_path = CFG_PATH
    
    if base_cfg.benchmark.enable:
        await run_autotune(CFG_PATH)
        if os.path.exists("bm_cfg.json"):
            active_cfg_path = "bm_cfg.json"
            logger.info(f"⚡ БЕНЧМАРК АКТИВЕН: Движок переключен на {active_cfg_path}")

    # Загружаем рабочий конфиг для инициализации Telegram бота
    active_cfg = load_config(active_cfg_path)
    tg_bot = TelegramSender(active_cfg.telegram.bot_token, active_cfg.telegram.chat_id) if active_cfg.telegram.enable else None
    
    # ---> НОВОЕ: ПУШ НАСТРОЕК ПРИ СТАРТЕ <---
    if tg_bot and active_cfg.telegram.enable:
        startup_msg = ResultFormatter.build_startup_message(active_cfg, active_cfg_path)
        await tg_bot.send_message(startup_msg)
        logger.info("🚀 Стартовое сообщение с настройками отправлено в Telegram.")
    
    while True:
        try:
            cfg = load_config(active_cfg_path)
            scanner = CandidateScanner(cfg)
            
            await run_scanner_cycle(scanner, cfg, tg_bot)
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