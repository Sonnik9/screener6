import time
import webbrowser
import logging
import random
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Clicker")

ROOT_DIR = Path(__file__).resolve().parent
RESULTS_FILE = ROOT_DIR / "target_links.txt"

def open_links_in_browser(links):
    """Открывает список ссылок в браузере."""
    for link in links:
        logger.info(f"🌐 Открываю вкладку: {link}")
        webbrowser.open_new_tab(link)
        sleep_time = random.uniform(2.30, 5.70)  # Случайная задержка между открытием вкладок
        time.sleep(sleep_time)

def main():
    logger.info("Запуск ручного кликера...")
    
    if not RESULTS_FILE.exists():
        logger.warning(f"Файл {RESULTS_FILE} не найден. Нечего открывать.")
        return

    # Читаем ссылки из файла
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        links = [line.strip() for line in f.readlines() if line.strip()]

    if not links:
        logger.info("Файл со ссылками пуст. Новых монет пока нет.")
        return

    logger.info(f"Найдено {len(links)} ссылок. Начинаю открывать...")
    
    open_links_in_browser(links)
    
    # Очищаем файл, чтобы не открыть эти же вкладки во время следующего ручного запуска
    open(RESULTS_FILE, "w").close()
    logger.info("Все вкладки открыты! Файл со ссылками очищен. Скрипт завершил работу.")

if __name__ == "__main__":
    main()