## CRITICAL

## (Помним и стремимся к главной цели скринера -- искать монеты похожие паттерну который представлен на фото (target_pattern_1m.png). Бот, в своем нынешнем состоянии не достиг цели поиска таких монет. Возможно слишком много переменных. Поэтому в следующей, 9й версии, мы постараемся решить эту задачу по поиску таких монет, и меняем подход к делу -- упращаем задачу по-человечески. В благоприятном случае будет максимум до 5 целевых монет в моменте. Монеты близкие по смыслу приветсвуются)

---

## ЗАКРЫТЫЕ ЗАДАЧИ (v9)

1. ✅ Wicks упрощены:
    - Убрано всё лишнее (long_wick_ratio, dominant_wick_share, body_floor_*, two_sided_*, reclaim из wicks).
    - Оставлено чистое соотношение `(high - low) / abs(open - close)` для свечей где `(high/low - 1)*100 >= min_pct_range` и тело > 0 и диапазон > 0.
    - Добавлен `min_pct_range` — порог проверки диапазона.
    - Добавлен счётчик `wick_count` (+ `wick_share`), фильтр `min_wick_count`.

2. ✅ Donchain range добавлен:
    - Индикатор: `(mean(highs[-window:]) / mean(lows[-window:]) - 1) * 100`
    - Параметры: `window`, `min_donchain_range`, `max_donchain_range`
    - PRIMARY-фича с весом 0.10 в scoring.

3. ✅ reverse → benchmark:
    - Конфиг: `cfg.json` ключ `reverse` переименован в `benchmark`.
    - `AppConfig.reverse` → `AppConfig.benchmark` (класс `BenchmarkSection`).
    - Backward compat: старые cfg с ключом `reverse` продолжают работать.
    - `benchmark_pipeline.py` обновлён (убраны ссылки на `reverse_cfg`).

4. ✅ Всё остальное задокументировано как второстепенное/опциональное:
    - `regime`, `axis`, `wall`, `activity`, `reclaim`, `liquidity` — все имеют `_doc` с пометкой "Второстепенное/опциональное".
    - В `CFG_TEMPLATE` (config.py) те же комментарии inline.

5. ✅ Рефакторинг завершён, ветка переименована v7 → v9.

6. ✅ Дублирование убрано:
    - `reverse_runtime_cfg.json` больше не пишется.
    - Остался только один runtime cfg файл: `bm_cfg.json`.
    - `benchmark_pipeline.py`: `_write_bm_cfg()` пишет только в `bm_cfg.json`.

7. ✅ Код готов к запуску (`python main.py`).
