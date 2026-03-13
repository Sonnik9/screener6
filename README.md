# britva_bot v6.6

Скринер для поиска 1m-монет под паттерн типа «волатильный боковик вокруг оси с длинными тенями и упором в стенку».

## Что теперь делает `main.py`

`main.py` работает в двух режимах:

1. **Обычный скан по `filter` из `cfg.json`** — если `reverse.enabled=false`.
2. **Benchmark-калибровка + скан** — если `reverse.enabled=true` и список `reverse.benchmarks` не пустой (в этом режиме создаётся отдельный runtime-конфиг).

То есть теперь включение benchmark-фильтра делается **только явным булевым флагом**, без магии вида `preset_mode: recommended`.

## Новый формат `reverse` в `cfg.json`

```json
"reverse": {
  "enabled": false,
  "step_min": 5,
  "slot": "base",
  "benchmarks": [
    {
      "symbol": "WILDUSDT",
      "start": "2026-02-24T18:00:00+00:00",
      "end": "2026-02-24T19:00:00+00:00",
      "slot": "base"
    }
  ]
}
```

### Смысл полей

- `enabled` — включает или полностью выключает benchmark-калибровку.
- `step_min` — шаг семплирования для `reverse.py`.
- `slot` — слот `soft | base | strict`, который будет использоваться по умолчанию.
- `benchmarks[].slot` — необязательный override для конкретного эталона.

Если `benchmarks[].slot` не указан, берётся общий `reverse.slot`.

## Форматы времени для benchmarks

Поддерживаются оба формата времени:

- ISO UTC строка: `2026-02-24T21:00:00+00:00`
- UTC milliseconds: `1771966800000`

## Хелпер времени

```bash
python time_helper.py to-ms 2026-02-24T21:00:00+00:00
python time_helper.py to-iso 1771966800000
```

## Какие файлы появляются после запуска `main.py`

- `candidates.json` — итоговый скан

- `cfg.json` — базовый конфиг остаётся неизменным
- `bm_cfg.json` — основной runtime-конфиг с вычисленным benchmark `filter`, который используется сканером только при `reverse.enabled=true`
- `reverse_runtime_cfg.json` — совместимый дубликат runtime-конфига для старого пайплайна

- `cfg.json` не перезаписывается benchmark-параметрами

- `reverse_runs/reverse_*.json` — отдельные отчёты по каждому эталону
- `reverse_runs/reverse_*_slots.json` — ready-to-paste слоты по каждому эталону

## Документация в `cfg.json`

Теперь сам `cfg.json` можно читать как справочник:

- все поясняющие ключи начинаются с `_`
- загрузчик конфига автоматически их игнорирует
- можно спокойно оставлять `_doc`, `_fields`, `_workflow` прямо внутри файла

Это позволяет документировать реальные параметры рядом с их значениями и не ломать JSON-парсер.

## Быстрый старт

```bash
python main.py
```

## Что есть в `candidates.json`

Для каждой найденной или рекомендованной монеты теперь есть:

- `metrics` — сырые расчётные метрики
- `filter_metrics` — срез «какие пороги дала бы сама монета»
- `active_filter` — какой фильтр реально применялся при этом запуске
- `filter_checks` — что именно монета прошла / не прошла

Плюс сверху есть быстрые списки:

- `candidate_symbols`
- `recommended_symbols`
- `candidate_quick_list`
- `recommended_quick_list`
