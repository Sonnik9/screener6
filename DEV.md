## LITE

{
  "_workflow": {
    "mode_switch": "reverse.enabled=false -> обычный скан по filter из этого файла; reverse.enabled=true -> сначала benchmark-калибровка, потом скан.",
    "doc_keys": "Любые ключи, начинающиеся с _, используются как документация и игнорируются загрузчиком.",
    "wicks_focus_hint": "Если хочешь делать акцент только на фитилеобразности, оставляй wicks.enabled=true, а regime/axis/wall/activity/reclaim/liquidity можно временно выключать по месту."
  },
  "app": {
    "_doc": "Базовые настройки прохода по рынку.",
    "_fields": {
      "quote": "Котируемая валюта для отбора фьючерсов. Обычно USDT.",
      "max_symbols": "0 = брать все доступные символы. Любое положительное число = жёсткий лимит количества инструментов.",
      "concurrent_symbols": "Сколько символов анализировать параллельно.",
      "top_n": "Сколько лучших кандидатов и near miss хранить в итоговом JSON.",
      "request_interval_ms": "Пауза между REST-запросами на свечи. Нужна против rate limit (429). Рекомендовано 250-350+ ms."
    },
    "quote": "USDT",
    "max_symbols": 0,
    "concurrent_symbols": 3,
    "top_n": 20,
    "request_interval_ms": 250
  },
  "exchange": {
    "_doc": "Секция под сетевые и приватные параметры. Для скринера в публичном режиме ключи могут быть пустыми.",
    "proxy": "",
    "api_key": "",
    "api_secret": ""
  },
  "reverse": {
    "_doc": "Управление benchmark-калибровкой. Это отдельный шаг, который строит filter по эталонным окнам. Теперь включается только явным булевым флагом.",
    "_fields": {
      "enabled": "false = main.py не трогает benchmarks и использует обычный filter ниже. true = сначала reverse по эталонам, потом scan.",
      "step_min": "Шаг семплирования внутри reverse.py. Меньше шаг = подробнее, но дольше.",
      "slot": "Какой слот брать из reverse-отчёта по умолчанию: soft | base | strict.",
      "benchmarks": "Список эталонных окон. Для каждого можно задать свой slot и свой step_min."
    },
    "enabled": true,
    "step_min": 5,
    "slot": "soft",
    "benchmarks": [
      {
        "_doc": "Эталонный участок рынка. (Это и есть паттерн который на фото. Можно указывать start/end в ISO UTC, либо start_ms/end_ms в UTC milliseconds.",
        "symbol": "WILDUSDT",
        "start": "2026-02-24T18:04:00+00:00",
        "end": "2026-02-24T19:04:00+00:00",
        "slot": "soft"
      }
    ]
  },
  "filter": {
    "_doc": "Основной фильтр паттерна. Именно он применяется напрямую, если reverse.enabled=false.",
    "_fields": {
      "timeframe": "Таймфрейм свечей. Для этой задачи обычно 1m.",
      "lookback_candles": "Размер окна анализа в свечах.",
      "min_score_pct": "Минимальный итоговый score для прохода. Даже если все секции отключены, score-порог остаётся глобальным.",
      "approximation": "Толерантность соответствия эталону: enabled=false -> работает как раньше через min_score_pct; enabled=true -> порог score берётся из min_match_pct (например 80)."
    },
    "timeframe": "1m",
    "lookback_candles": 60,
    "min_score_pct": 78.0,
    "approximation": {
      "enabled": true,
      "min_match_pct": 76.0
    },
    "regime": {
      "_doc": "Фильтр общей геометрии боковика: ширина коридора, чоповость, нетрендовость.",
      "enabled": true,
      "min_corridor_pct": 3.0,
      "max_corridor_pct": 9.4,
      "quantile_low": 0.10,
      "quantile_high": 0.90,
      "min_chop": 58.0,
      "max_efficiency_ratio": 0.22,
      "max_slope_to_corridor_ratio": 1.10
    },
    "wicks": {
      "_doc": "Ключевая секция для текущей гипотезы. Оценивает доминирование теней над телами и долю 'колючих' свечей.",
      "_fields": {
        "long_wick_ratio": "Свеча считается длиннофитильной, если dominant_wick / body >= этого значения.",
        "min_dominant_wick_share": "Минимальная доля dominant wick от полного диапазона свечи.",
        "body_floor_pct": "Минимальный абсолютный floor тела в процентах цены, чтобы деление на почти ноль не разносило ratio.",
        "body_floor_range_share": "Минимальный floor тела как доля свечного диапазона.",
        "min_avg_wick_ratio": "Минимальное среднее отношение фитиля к телу по окну.",
        "min_long_wick_share": "Минимальная доля свечей, которые считаются длиннофитильными.",
        "min_two_sided_wick_share": "Минимальная доля свечей с фитилями с обеих сторон.",
        "min_two_sided_share_per_candle": "Минимальная доля диапазона, которую должны занимать оба фитиля по отдельности, чтобы свеча считалась truly two-sided.",
        "max_two_sided_imbalance": "Максимальный допустимый перекос верхнего и нижнего фитиля у two-sided свечей."
      },
      "enabled": true,
      "long_wick_ratio": 1.48,
      "min_dominant_wick_share": 0.26,
      "body_floor_pct": 0.009,
      "body_floor_range_share": 0.036,
      "min_avg_wick_ratio": 1.40,
      "min_long_wick_share": 0.30,
      "min_two_sided_wick_share": 0.15,
      "min_two_sided_share_per_candle": 0.07,
      "max_two_sided_imbalance": 3.8
    },
    "axis": {
      "_doc": "Возвраты к оси/центру диапазона. Полезно для mean-reversion паттерна.",
      "enabled": true,
      "tolerance_pct": 0.36,
      "recent_window": 24,
      "min_axis_touch_share": 0.42,
      "min_recent_axis_touches": 2,
      "min_rotation_count": 16,
      "mode_bins": 27,
      "use_hlc3": true,
      "close_weight": 0.40,
      "hlc3_weight": 0.60
    },
    "wall": {
      "_doc": "Прижатие к верхней или нижней стенке диапазона.",
      "enabled": false,
      "touch_tolerance_pct": 0.35,
      "recent_window": 18,
      "min_recent_wall_touch_share": 0.0,
      "min_full_wall_touch_share": 0.05,
      "top_k_highs": 8,
      "bottom_k_lows": 8,
      "max_cluster_spread_pct": 1.2
    },
    "activity": {
      "_doc": "Насколько активно цена бегает внутри диапазона и возвращается к оси.",
      "enabled": true,
      "min_path_to_corridor_ratio": 9.6,
      "ema_period": 16,
      "axis_band_pct": 0.28,
      "min_return_to_axis_count": 6
    },
    "reclaim": {
      "_doc": "Ложные проколы с возвратом обратно внутрь диапазона.",
      "enabled": false,
      "lookback": 6,
      "min_false_break_reclaim_share": 0.12
    },
    "liquidity": {
      "_doc": "Грубый фильтр ликвидности. Для отладки можно держать выключенным.",
      "enabled": false,
      "min_avg_quote_turnover": 0.0
    }
  }
}


## MEDIUM

{
  "_workflow": {
    "mode_switch": "reverse.enabled=false -> обычный скан по filter из этого файла; reverse.enabled=true -> сначала benchmark-калибровка, потом скан.",
    "doc_keys": "Любые ключи, начинающиеся с _, используются как документация и игнорируются загрузчиком.",
    "wicks_focus_hint": "Если хочешь делать акцент только на фитилеобразности, оставляй wicks.enabled=true, а regime/axis/wall/activity/reclaim/liquidity можно временно выключать по месту."
  },
  "app": {
    "_doc": "Базовые настройки прохода по рынку.",
    "_fields": {
      "quote": "Котируемая валюта для отбора фьючерсов. Обычно USDT.",
      "max_symbols": "0 = брать все доступные символы. Любое положительное число = жёсткий лимит количества инструментов.",
      "concurrent_symbols": "Сколько символов анализировать параллельно.",
      "top_n": "Сколько лучших кандидатов и near miss хранить в итоговом JSON.",
      "request_interval_ms": "Пауза между REST-запросами на свечи. Нужна против rate limit (429). Рекомендовано 250-350+ ms."
    },
    "quote": "USDT",
    "max_symbols": 0,
    "concurrent_symbols": 3,
    "top_n": 20,
    "request_interval_ms": 250
  },
  "exchange": {
    "_doc": "Секция под сетевые и приватные параметры. Для скринера в публичном режиме ключи могут быть пустыми.",
    "proxy": "",
    "api_key": "",
    "api_secret": ""
  },
  "reverse": {
    "_doc": "Управление benchmark-калибровкой. Это отдельный шаг, который строит filter по эталонным окнам. Теперь включается только явным булевым флагом.",
    "_fields": {
      "enabled": "false = main.py не трогает benchmarks и использует обычный filter ниже. true = сначала reverse по эталонам, потом scan.",
      "step_min": "Шаг семплирования внутри reverse.py. Меньше шаг = подробнее, но дольше.",
      "slot": "Какой слот брать из reverse-отчёта по умолчанию: soft | base | strict.",
      "benchmarks": "Список эталонных окон. Для каждого можно задать свой slot и свой step_min."
    },
    "enabled": true,
    "step_min": 5,
    "slot": "base",
    "benchmarks": [
      {
        "_doc": "Эталонный участок рынка. (Это и есть паттерн который на фото. Можно указывать start/end в ISO UTC, либо start_ms/end_ms в UTC milliseconds.",
        "symbol": "WILDUSDT",
        "start": "2026-02-24T18:04:00+00:00",
        "end": "2026-02-24T19:04:00+00:00",
        "slot": "base"
      }
    ]
  },
  "filter": {
    "_doc": "Основной фильтр паттерна. Именно он применяется напрямую, если reverse.enabled=false.",
    "_fields": {
      "timeframe": "Таймфрейм свечей. Для этой задачи обычно 1m.",
      "lookback_candles": "Размер окна анализа в свечах.",
      "min_score_pct": "Минимальный итоговый score для прохода. Даже если все секции отключены, score-порог остаётся глобальным.",
      "approximation": "Толерантность соответствия эталону: enabled=false -> работает как раньше через min_score_pct; enabled=true -> порог score берётся из min_match_pct (например 80)."
    },
    "timeframe": "1m",
    "lookback_candles": 60,
    "min_score_pct": 84.0,
    "approximation": {
      "enabled": true,
      "min_match_pct": 82.0
    },
    "regime": {
      "_doc": "Фильтр общей геометрии боковика: ширина коридора, чоповость, нетрендовость.",
      "enabled": true,
      "min_corridor_pct": 3.6,
      "max_corridor_pct": 8.2,
      "quantile_low": 0.12,
      "quantile_high": 0.88,
      "min_chop": 64.0,
      "max_efficiency_ratio": 0.16,
      "max_slope_to_corridor_ratio": 0.95
    },
    "wicks": {
      "_doc": "Ключевая секция для текущей гипотезы. Оценивает доминирование теней над телами и долю 'колючих' свечей.",
      "_fields": {
        "long_wick_ratio": "Свеча считается длиннофитильной, если dominant_wick / body >= этого значения.",
        "min_dominant_wick_share": "Минимальная доля dominant wick от полного диапазона свечи.",
        "body_floor_pct": "Минимальный абсолютный floor тела в процентах цены, чтобы деление на почти ноль не разносило ratio.",
        "body_floor_range_share": "Минимальный floor тела как доля свечного диапазона.",
        "min_avg_wick_ratio": "Минимальное среднее отношение фитиля к телу по окну.",
        "min_long_wick_share": "Минимальная доля свечей, которые считаются длиннофитильными.",
        "min_two_sided_wick_share": "Минимальная доля свечей с фитилями с обеих сторон.",
        "min_two_sided_share_per_candle": "Минимальная доля диапазона, которую должны занимать оба фитиля по отдельности, чтобы свеча считалась truly two-sided.",
        "max_two_sided_imbalance": "Максимальный допустимый перекос верхнего и нижнего фитиля у two-sided свечей."
      },
      "enabled": true,
      "long_wick_ratio": 1.65,
      "min_dominant_wick_share": 0.29,
      "body_floor_pct": 0.010,
      "body_floor_range_share": 0.040,
      "min_avg_wick_ratio": 1.55,
      "min_long_wick_share": 0.34,
      "min_two_sided_wick_share": 0.18,
      "min_two_sided_share_per_candle": 0.08,
      "max_two_sided_imbalance": 3.4
    },
    "axis": {
      "_doc": "Возвраты к оси/центру диапазона. Полезно для mean-reversion паттерна.",
      "enabled": true,
      "tolerance_pct": 0.30,
      "recent_window": 24,
      "min_axis_touch_share": 0.48,
      "min_recent_axis_touches": 3,
      "min_rotation_count": 20,
      "mode_bins": 29,
      "use_hlc3": true,
      "close_weight": 0.45,
      "hlc3_weight": 0.55
    },
    "wall": {
      "_doc": "Прижатие к верхней или нижней стенке диапазона.",
      "enabled": false,
      "touch_tolerance_pct": 0.35,
      "recent_window": 18,
      "min_recent_wall_touch_share": 0.0,
      "min_full_wall_touch_share": 0.05,
      "top_k_highs": 8,
      "bottom_k_lows": 8,
      "max_cluster_spread_pct": 1.2
    },
    "activity": {
      "_doc": "Насколько активно цена бегает внутри диапазона и возвращается к оси.",
      "enabled": true,
      "min_path_to_corridor_ratio": 11.8,
      "ema_period": 18,
      "axis_band_pct": 0.24,
      "min_return_to_axis_count": 8
    },
    "reclaim": {
      "_doc": "Ложные проколы с возвратом обратно внутрь диапазона.",
      "enabled": false,
      "lookback": 6,
      "min_false_break_reclaim_share": 0.12
    },
    "liquidity": {
      "_doc": "Грубый фильтр ликвидности. Для отладки можно держать выключенным.",
      "enabled": false,
      "min_avg_quote_turnover": 0.0
    }
  }
}




## STRONG

{
  "_workflow": {
    "mode_switch": "reverse.enabled=false -> обычный скан по filter из этого файла; reverse.enabled=true -> сначала benchmark-калибровка, потом скан.",
    "doc_keys": "Любые ключи, начинающиеся с _, используются как документация и игнорируются загрузчиком.",
    "wicks_focus_hint": "Если хочешь делать акцент только на фитилеобразности, оставляй wicks.enabled=true, а regime/axis/wall/activity/reclaim/liquidity можно временно выключать по месту."
  },
  "app": {
    "_doc": "Базовые настройки прохода по рынку.",
    "_fields": {
      "quote": "Котируемая валюта для отбора фьючерсов. Обычно USDT.",
      "max_symbols": "0 = брать все доступные символы. Любое положительное число = жёсткий лимит количества инструментов.",
      "concurrent_symbols": "Сколько символов анализировать параллельно.",
      "top_n": "Сколько лучших кандидатов и near miss хранить в итоговом JSON.",
      "request_interval_ms": "Пауза между REST-запросами на свечи. Нужна против rate limit (429). Рекомендовано 250-350+ ms."
    },
    "quote": "USDT",
    "max_symbols": 0,
    "concurrent_symbols": 3,
    "top_n": 20,
    "request_interval_ms": 250
  },
  "exchange": {
    "_doc": "Секция под сетевые и приватные параметры. Для скринера в публичном режиме ключи могут быть пустыми.",
    "proxy": "",
    "api_key": "",
    "api_secret": ""
  },
  "reverse": {
    "_doc": "Управление benchmark-калибровкой. Это отдельный шаг, который строит filter по эталонным окнам. Теперь включается только явным булевым флагом.",
    "_fields": {
      "enabled": "false = main.py не трогает benchmarks и использует обычный filter ниже. true = сначала reverse по эталонам, потом scan.",
      "step_min": "Шаг семплирования внутри reverse.py. Меньше шаг = подробнее, но дольше.",
      "slot": "Какой слот брать из reverse-отчёта по умолчанию: soft | base | strict.",
      "benchmarks": "Список эталонных окон. Для каждого можно задать свой slot и свой step_min."
    },
    "enabled": true,
    "step_min": 5,
    "slot": "strict",
    "benchmarks": [
      {
        "_doc": "Эталонный участок рынка. (Это и есть паттерн который на фото. Можно указывать start/end в ISO UTC, либо start_ms/end_ms в UTC milliseconds.",
        "symbol": "WILDUSDT",
        "start": "2026-02-24T18:04:00+00:00",
        "end": "2026-02-24T19:04:00+00:00",
        "slot": "strict"
      }
    ]
  },
  "filter": {
    "_doc": "Основной фильтр паттерна. Именно он применяется напрямую, если reverse.enabled=false.",
    "_fields": {
      "timeframe": "Таймфрейм свечей. Для этой задачи обычно 1m.",
      "lookback_candles": "Размер окна анализа в свечах.",
      "min_score_pct": "Минимальный итоговый score для прохода. Даже если все секции отключены, score-порог остаётся глобальным.",
      "approximation": "Толерантность соответствия эталону: enabled=false -> работает как раньше через min_score_pct; enabled=true -> порог score берётся из min_match_pct (например 80)."
    },
    "timeframe": "1m",
    "lookback_candles": 60,
    "min_score_pct": 90.0,
    "approximation": {
      "enabled": true,
      "min_match_pct": 88.0
    },
    "regime": {
      "_doc": "Фильтр общей геометрии боковика: ширина коридора, чоповость, нетрендовость.",
      "enabled": true,
      "min_corridor_pct": 4.1,
      "max_corridor_pct": 6.4,
      "quantile_low": 0.14,
      "quantile_high": 0.86,
      "min_chop": 69.0,
      "max_efficiency_ratio": 0.10,
      "max_slope_to_corridor_ratio": 0.78
    },
    "wicks": {
      "_doc": "Ключевая секция для текущей гипотезы. Оценивает доминирование теней над телами и долю 'колючих' свечей.",
      "_fields": {
        "long_wick_ratio": "Свеча считается длиннофитильной, если dominant_wick / body >= этого значения.",
        "min_dominant_wick_share": "Минимальная доля dominant wick от полного диапазона свечи.",
        "body_floor_pct": "Минимальный абсолютный floor тела в процентах цены, чтобы деление на почти ноль не разносило ratio.",
        "body_floor_range_share": "Минимальный floor тела как доля свечного диапазона.",
        "min_avg_wick_ratio": "Минимальное среднее отношение фитиля к телу по окну.",
        "min_long_wick_share": "Минимальная доля свечей, которые считаются длиннофитильными.",
        "min_two_sided_wick_share": "Минимальная доля свечей с фитилями с обеих сторон.",
        "min_two_sided_share_per_candle": "Минимальная доля диапазона, которую должны занимать оба фитиля по отдельности, чтобы свеча считалась truly two-sided.",
        "max_two_sided_imbalance": "Максимальный допустимый перекос верхнего и нижнего фитиля у two-sided свечей."
      },
      "enabled": true,
      "long_wick_ratio": 1.82,
      "min_dominant_wick_share": 0.31,
      "body_floor_pct": 0.011,
      "body_floor_range_share": 0.043,
      "min_avg_wick_ratio": 1.72,
      "min_long_wick_share": 0.38,
      "min_two_sided_wick_share": 0.21,
      "min_two_sided_share_per_candle": 0.095,
      "max_two_sided_imbalance": 3.0
    },
    "axis": {
      "_doc": "Возвраты к оси/центру диапазона. Полезно для mean-reversion паттерна.",
      "enabled": true,
      "tolerance_pct": 0.25,
      "recent_window": 24,
      "min_axis_touch_share": 0.54,
      "min_recent_axis_touches": 3,
      "min_rotation_count": 25,
      "mode_bins": 31,
      "use_hlc3": true,
      "close_weight": 0.50,
      "hlc3_weight": 0.50
    },
    "wall": {
      "_doc": "Прижатие к верхней или нижней стенке диапазона.",
      "enabled": false,
      "touch_tolerance_pct": 0.35,
      "recent_window": 18,
      "min_recent_wall_touch_share": 0.0,
      "min_full_wall_touch_share": 0.05,
      "top_k_highs": 8,
      "bottom_k_lows": 8,
      "max_cluster_spread_pct": 1.2
    },
    "activity": {
      "_doc": "Насколько активно цена бегает внутри диапазона и возвращается к оси.",
      "enabled": true,
      "min_path_to_corridor_ratio": 13.8,
      "ema_period": 20,
      "axis_band_pct": 0.20,
      "min_return_to_axis_count": 10
    },
    "reclaim": {
      "_doc": "Ложные проколы с возвратом обратно внутрь диапазона.",
      "enabled": false,
      "lookback": 6,
      "min_false_break_reclaim_share": 0.12
    },
    "liquidity": {
      "_doc": "Грубый фильтр ликвидности. Для отладки можно держать выключенным.",
      "enabled": false,
      "min_avg_quote_turnover": 0.0
    }
  }
}