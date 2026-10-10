# Tender Hack 2026 — автозаполнение характеристик СТЕ и подбор КТРУ

Сервис принимает свободное описание товара («Стол офисный ЛДСП высота 750 мм цвет серый»),
выделяет характеристики, приводит названия и единицы измерения к виду КТРУ, поэтапно сужает
множество кодов КТРУ до конечного кода (группы вариаций) и сообщает об ошибках:
недопустимые значения, выход за диапазон, неверные единицы, опечатки, незаполненные
обязательные характеристики.

Скоуп: одежда, мебель, инструменты. Приоритет источников характеристик:
КТРУ → частотные характеристики портала → новое свойство.

## Требования

- Python 3.11+ (Linux или Windows)
- зависимости: `pip install -r requirements.txt`
  (FastAPI, uvicorn, pydantic, rapidfuzz, numpy, lxml, openpyxl, pytest)
- ML-моделей и внешних API нет: только rapidfuzz и SQLite

## Материалы

Нужна распакованная папка с материалами организаторов «Казань 2026»:

```
Казань 2026/
  КТРУ/КТРУ xml.zip           # справочник КТРУ (zip с вложенными zip-частями)
  Выгрузки портала/*.xlsx     # мебель, одежда, инструменты
```

Сам `КТРУ xml.zip` вручную распаковывать **не нужно**: `build_index.py` читает вложенные
zip-части напрямую и разбирает все файлы `nsiKTRUNew_all_actual_*.xml`
(файлы not-actual и позиции со статусами INACTIVE/TERMINATED пропускаются).
Если материалы лежат одним архивом, путь к нему можно передать в `--materials`:
архив будет распакован в `_materials/`.

## Сборка индекса

```bash
python -m scripts.build_index --materials "/path/to/Казань 2026"
# Windows (пример):
python -m scripts.build_index --materials C:\Users\Asus\Desktop\Vtoroy_work\Kazan2026_unzipped
```

- сборка занимает около 70 с, результат — `data/processed/catalog.db` (~120 МБ, в git не попадает);
- по умолчанию разбираются **все** части КТРУ: в базе должно получиться 3391 позиция
  (мебель 355, одежда 1522, инструменты 1514 — итог печатается в конце сборки);
  `--ktru-files N` ограничивает число частей (только для отладки: с малым N индекс неполный
  и качество подбора резко падает), `--ste-limit` — число СТЕ
  на категорию (по умолчанию 20000), `--db` — другой путь к базе;
- в базе: `ktru` (активные позиции в скоупе, ~3.4 тыс.), `ktru_char_values`
  (допустимые значения, диапазоны min/max, единицы ОКЕИ), `portal_ste`, `portal_chars`.

Если catalog.db открыт другим процессом (сервером), соберите базу в другой файл
(`--db data/processed/catalog_new.db`) и замените ею старую после остановки сервера.

### Переменная CATALOG_DB

Путь к базе по умолчанию — `data/processed/catalog.db`. Чтобы использовать другую базу:

```bash
export CATALOG_DB=/path/to/catalog.db        # Linux
$env:CATALOG_DB="C:\path\to\catalog.db"      # Windows PowerShell
```

## Запуск

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

UI: http://localhost:8000, документация API: http://localhost:8000/docs.
Каталог загружается в память при старте (~0.6 с), один запрос обрабатывается за ~50 мс (p95 < 100 мс).

## Тесты и QA

```bash
pytest -q                 # юнит-тесты; тесты движка пропускаются, если catalog.db не собран
python qa/run_eval.py     # из ветки QA (папка qa/ с cases.csv); пишет qa/results.csv и qa/summary.md
```

Чтобы прогнать QA на этой ветке, достаточно `PYTHONPATH=<папка этой ветки>` и, при необходимости,
`CATALOG_DB`.

## API

`POST /api/analyze`

```json
{
  "text": "Стол письменный высота 820 кг",
  "domain_hint": "furniture",
  "characteristics": [{"name": "Цвет", "value": "серый", "unit": null}]
}
```

`domain_hint` (furniture | clothing | tools) и `characteristics` необязательны. Переданные
характеристики перекрывают распознанные из текста (по имени) и всегда возвращаются в ответе,
в том числе строки с пустым значением.

Ответ (основные поля):

| поле | содержание |
|---|---|
| `status` | `ok` · `need_more` · `ambiguous` · `error` (любая ошибка уровня error исключает `ok`) |
| `best_ktru` | `{code, name, okpd2, score, required_chars, matched_chars}` |
| `candidates[]` | до 5 `{code, name, score}`, если подходят несколько кодов |
| `characteristics[]` | `{name, value, unit, source: ktru\|portal\|new, user_input, required, allowed, min, max}`; `allowed` — список допустимых значений КТРУ или `null`, `min`/`max` — числовой диапазон в `unit` |
| `issues[]` | `{type, field, value, expected, suggestions[≤3], message, severity: error\|warning}`; `type`: `not_allowed`, `out_of_range`, `unit`, `mismatch`, `missing`, `typo`, а также `ambiguous`, `new_property` |
| `narrowing[]` | `{step, label, remaining, removed, reason, removed_codes[≤10]}`; шаги: «Домен» (исходный пул) → «Наименование» → «ОКПД2» → по одному шагу на каждую введённую характеристику → «Итог» |
| `next_steps[]` | что уточнить или исправить |
| `debug.elapsed_ms` | время обработки запроса |

Старые поля (`kind`, `suggestion`, `stage`, `top`, `note`, `raw_name`, `canonical_name`)
сохранены для обратной совместимости.

## Структура

```
app/
  main.py       FastAPI, статика UI
  engine.py     сквозной сценарий запроса
  parser.py     разбор текста, домен, наименование, транслитерация
  catalog.py    кэш КТРУ/портала в памяти
  matcher.py    поэтапное сужение и причины отсева
  unify.py      унификация характеристик (КТРУ → портал → новое)
  validate.py   проверка значений, диапазонов и единиц
  units.py      единицы измерения и пересчёт
scripts/build_index.py   сборка catalog.db
frontend/                статический UI
docs/                    BPMN
tests/
```

## Ограничения ТЗ

- без проприетарных LLM (в том числе через роутеры), без платных поисковых API, без low-code/no-code;
- открытые модели допустимы при суммарном объёме VRAM ≤ 40 ГБ (в текущей версии моделей нет).
