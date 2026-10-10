# Tender Hack 2026 — автозаполнение характеристик СТЕ и подбор кода КТРУ

Сервис принимает свободное описание товара («Стол офисный ЛДСП высота 750 мм цвет серый»),
выделяет характеристики, приводит названия и единицы к виду КТРУ и пошагово сужает
множество кодов КТРУ до конечного кода (группы вариаций). Он явно сообщает об ошибках:
недопустимые значения, выход за диапазон, неверные единицы, опечатки, незаполненные
обязательные характеристики. Домены: мебель, одежда, инструменты. Порядок источников
характеристик: КТРУ → частотные характеристики портала → новое свойство. Без LLM и внешних API.

## Требования

- Python **3.11** (проверено на 3.11.9; на Linux тесты без базы прошли и на 3.13).
- ОС: Windows 10/11, Linux (x86_64); macOS — не проверено.
- RAM: сборка индекса — пик ~410 МБ, сервер — ~130 МБ после загрузки каталога.
  Рекомендуется от 2 ГБ свободной памяти.
- Диск: ~160 МБ архив материалов + ~120 МБ `catalog.db` + ~250 МБ venv.
- Зависимости: `requirements.txt` (FastAPI, uvicorn, pydantic, rapidfuzz, numpy, lxml, openpyxl, pytest).

## Данные

Архив организаторов «Казань 2026»: https://disk.yandex.ru/d/5Olg3IoYYf4loA

После распаковки ожидается структура:

```
Казань 2026/
  Критерии_оценки_для_методички_участникам_Казани_20261006.docx
  Презентация Задачи_Хакатон_Казань_20261009_1900_pdf.pdf
  КТРУ/
    КТРУ xml.zip                          # ~102 МБ, вложенные zip с nsiKTRUNew_all_actual_*.xml
    Описание структуры xml с КТРУ.docx
  Примеры выгрузок/
    Мебель.xlsx  Одежда.xlsx  Инструменты.xlsx
```

`КТРУ xml.zip` распаковывать **не нужно** — скрипт читает вложенные zip сам.

Встроенный распаковщик Windows («Извлечь всё») может записать русские имена папок
«кракозябрами» (`Љ§\xa0\xadм 2026\...`). Варианты:
- распаковать архив через **7-Zip** (имена сохраняются корректно);
- или просто переименовать верхнюю папку, например в `Kazan2026`, и передать её в `--materials` —
  имена вложенных папок и файлов скрипту не важны, файлы ищутся по расширению и содержимому.

`data/processed/catalog.db` **не хранится в git** (~120 МБ), его нужно собрать.

## Установка и запуск

### Windows (PowerShell)

```powershell
git clone https://github.com/Telman3000/Tender-Hack-2026-based-on-bots-.git
cd Tender-Hack-2026-based-on-bots-
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # при запрете скриптов: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
$env:PYTHONUTF8 = "1"
# путь к папке, где лежат «КТРУ\КТРУ xml.zip» и «Примеры выгрузок\*.xlsx», например:
python -m scripts.build_index --materials "C:\Users\Asus\Downloads\Kazan2026_unzipped\Казань 2026"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Linux (bash)

```bash
git clone https://github.com/Telman3000/Tender-Hack-2026-based-on-bots-.git
cd Tender-Hack-2026-based-on-bots-
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m scripts.build_index --materials "/path/to/Казань 2026"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### macOS (Intel и Apple Silicon) — не проверено на macOS

```bash
brew install python@3.11            # или установщик с https://www.python.org/downloads/
git clone https://github.com/Telman3000/Tender-Hack-2026-based-on-bots-.git
cd Tender-Hack-2026-based-on-bots-
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# архив с кириллическими именами распаковывать так (Finder/unzip могут исказить имена):
ditto -x -k "Казань 2026.zip" ~/Kazan2026        # или: brew install unar && unar "Казань 2026.zip"
python -m scripts.build_index --materials ~/Kazan2026
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Занятый порт: `lsof -i :8000`.

UI: http://127.0.0.1:8000/ , API: `POST http://127.0.0.1:8000/api/analyze`, Swagger: http://127.0.0.1:8000/docs

Сборка индекса (замер на чистом клоне, Windows, Python 3.11): **~60 с**, результат —
3030 позиций КТРУ (мебель 313, одежда 1408, инструменты 1309), 65 152 строки
допустимых значений, 60 000 СТЕ портала, `catalog.db` ≈ 120 МБ.
Установка venv + pip ≈ 40 с.

Параметры `build_index`: `--ktru-files N` — ограничить число частей КТРУ (только для
отладки, по умолчанию все), `--ste-limit` — число СТЕ на категорию (по умолчанию 20000),
`--db` — другой путь к базе. Путь к базе для сервера можно задать переменной `CATALOG_DB`.

### Docker

В репозитории есть `Dockerfile` и `docker-compose.yml`. Индекс собирается на хосте
(шаги выше), каталог `data/processed` монтируется в контейнер:

```bash
docker compose up --build      # http://127.0.0.1:8000/
```

**Не проверено:** Docker Desktop на тестовой машине установлен, но движок не был запущен (попытка запуска прервана), поэтому образ не собирался и нагрузочный тест контейнера не выполнялся.

## Проверка

```bash
python -m pytest -q            # 109 passed (без catalog.db часть тестов пропускается)
curl -s -X POST http://127.0.0.1:8000/api/analyze -H "Content-Type: application/json" \
     -d '{"text":"Стол офисный ЛДСП высота 750 мм ширина 1200 мм цвет серый"}'
python qa/run_eval.py          # 45 кейсов, пишет qa/results.csv и qa/summary.md
```

pytest может показать одно предупреждение `StarletteDeprecationWarning: Using httpx with
starlette.testclient is deprecated` — оно из FastAPI/Starlette TestClient, безвредно и на
работу сервиса не влияет.

В PowerShell тело запроса удобнее передать файлом: `curl.exe ... --data-binary "@req.json"`
(файл в UTF-8). Запрос: `{text, characteristics?: [{name, value, unit}], domain_hint?}`
(`domain_hint`: `furniture` | `clothing` | `tools`, иное значение → HTTP 422).

Сокращённый пример ответа на этот запрос (реальный ответ; выборочные элементы; полный список полей — в [docs/api.md](docs/api.md)):

```json
{
  "detected_domain": "furniture",
  "product_guess": "Стол офисный ЛДСП",
  "best_ktru": {"code": "31.01.10.000-00000004", "name": "Стол письменный", "okpd2": "31.01.1",
                "required_chars": ["Конфигурация стола", "Тип каркаса", "Вид материала столешницы",
                                   "Назначение стола письменного", "Вид материала каркаса"]},
  "status": "need_more",
  "characteristics": [
    {"name": "Высота", "value": "750", "unit": "мм", "source": "portal", "user_input": "высота 750 мм",
     "required": false, "allowed": null, "min": null, "max": null},
    {"name": "Вид материала столешницы", "value": "ЛДСП", "unit": null, "source": "ktru", "user_input": "лдсп",
     "required": true, "allowed": ["ДСП", "ЛДСП", "МДФ", "Массив дерева"], "min": null, "max": null},
    {"name": "Вид материала каркаса", "value": "", "unit": null, "source": "ktru", "user_input": null,
     "required": true, "allowed": ["Массив дерева", "МДФ", "ЛДСП", "ДСП"], "min": null, "max": null}
  ],
  "narrowing": [
    {"step": 1, "label": "Домен", "remaining": 355, "removed": 0, "reason": "Начальный пул КТРУ: домен «мебель»"},
    {"step": 2, "label": "Наименование", "remaining": 8, "removed": 347, "reason": "Сопоставление с наименованием «Стол офисный ЛДСП»"},
    {"step": 3, "label": "ОКПД2", "remaining": 3, "removed": 5, "reason": "Группы ОКПД2 лидеров: 31.01.1"},
    {"step": 4, "label": "Итог", "remaining": 3, "removed": 0, "reason": "Группа вариаций «Стол письменный»: 3 кодов"}
  ],
  "issues": [
    {"type": "missing", "kind": "missing", "field": "Конфигурация стола", "severity": "warning",
     "message": "Не заполнена обязательная характеристика КТРУ «Конфигурация стола»", "suggestions": ["Прямой", "Угловой"]}
  ],
  "debug": {"raw_count": 4, "elapsed_ms": 128.5}
}
```

Статусы: `code_status` (determined | ambiguous | not_found) — уверенность в коде,
`card_status` (complete | incomplete | invalid) — заполненность карточки, плюс `completeness`,
`corrections`, `span`, `next_steps_detail` (см. [docs/api.md](docs/api.md)). Старое поле `status`
сохранено: `not_found` > `error` > `need_more` > `ambiguous` > `ok`. Время ответа: медиана ~50 мс, в UI 70–200 мс.

Нагрузочный тест (`python scripts/load_test.py --url http://127.0.0.1:8802 --n 50 --concurrency 50 --pid <PID>`,
10 типовых запросов, Windows, Python 3.11, локальный uvicorn):

| Конфигурация | Запросов / параллельно | p50 | p95 | max | Пропускная способность | RSS до → после |
|---|---|---|---|---|---|---|
| 1 воркер | 50 / 50 | 4.2 с | 5.7 с | 5.7 с | 8.7 запр/с | 134 → 146 МБ |
| 1 воркер | 200 / 50 | 4.4 с | 5.5 с | 6.6 с | 12.2 запр/с | 146 → 153 МБ |
| `--workers 4` | 50 / 50 | 2.2 с | 2.3 с | 2.3 с | 21.4 запр/с | 533 → 556 МБ (все процессы) |

Один запрос обрабатывается ~50–100 мс CPU; при 50 одновременных запросах они встают в очередь,
поэтому задержка растёт линейно. Для нескольких пользователей запускайте `--workers N`
(каждый воркер держит свою копию каталога, ~130 МБ). RSS считается через `psutil` (если установлен).

QA (45 кейсов): верный код в топ-1 98%, в топ-3 100%.

Пакетная проверка: `POST /api/analyze/batch` (JSON, до 500 строк) и `POST /api/analyze/csv`
(CSV с одним столбцом наименований, UTF-8/cp1251, `;` или `,`, заголовок необязателен), оба умеют
построчный поток NDJSON (`?stream=1`). 100 строк — ~4 с. Контракт — в [docs/api.md](docs/api.md#пакетная-обработка).

```bash
curl -s -X POST "http://127.0.0.1:8000/api/analyze/csv?stream=1" -F "file=@names.csv"
```

Индекс КТРУ: берутся только файлы `all_actual` (файлы `all_not-actual` пропускаются) и позиции со статусом
не TERMINATED/INACTIVE; из нескольких версий одной позиции остаётся самая новая (`version`, затем
`updateDate`), а полностью одинаковые позиции (то же наименование, ОКПД2 и характеристики) сводятся
к одной, самой новой (при сборке — 361 такая позиция). Итог: 3030 позиций КТРУ в трёх доменах,
сборка индекса ~60 с.

## Частые проблемы

- **Нет или пустой `catalog.db`** — сервер вернёт ошибку/`not_found` на всё, тесты с базой
  пропускаются. Соберите индекс; проверьте, что в выводе 3030 позиций КТРУ.
- **Старый `catalog.db` от MVP** (≈864 позиции, без таблицы `ktru_char_values`) использовать
  нельзя — пересоберите. Если файл занят запущенным сервером: соберите в
  `--db data/processed/catalog_new.db` и переименуйте после остановки сервера.
- **Порт 8000 занят** — `--port 8001`; кто занял: `netstat -ano | findstr :8000` (Windows),
  `ss -ltnp | grep 8000` (Linux).
- **«Кракозябры» в консоли Windows** — `chcp 65001` и `$env:PYTHONUTF8 = "1"` перед запуском.

## Структура проекта

```
app/        main.py (FastAPI, UI), engine.py (оркестрация), parser.py (разбор текста),
            unify.py (сопоставление с КТРУ), matcher.py (пошаговое сужение), validate.py,
            units.py, catalog.py (кэш каталога), db.py, models.py, config.py
scripts/    build_index.py — сборка data/processed/catalog.db
frontend/   index.html, app.js, styles.css
tests/      pytest
qa/         cases.csv, run_eval.py, summary.md
docs/       документация
```

Документация:
[BPMN-процесс](docs/BPMN.md) ([process.bpmn](docs/process.bpmn), [process.png](docs/process.png)),
[схема компонентов](docs/components.png),
[презентация](docs/presentation.md),
[сценарий демо](docs/demo_script.md),
[ответы жюри](docs/jury_qa.md),
[простой питч](docs/pitch_simple.md).


## Метрики качества (QA, core 24411af + ui 4d6ae93 поверх main c6a89cd, 2026-10-10 21:26 MSK)

| Метрика | Основной набор (45) | Отложенный набор (45) |
|---|---|---|
| Код КТРУ на 1-м месте | 44 из 45 (98%) | 43 из 45 (96%) |
| Код в топ-3 | 45 из 45 (100%) | 44 из 45 (98%) |
| Статус верный | 45 из 45 (100%) | 43 из 45 (96%) |
| Ложные тревоги на чистых (ошибка) | 1 из 42 (2%) — H31, в карточке реальная ошибка (лобзик 2,1 г) | |
| Предупреждения на чистых (мягкие) | 3 из 42 (7%) | |
| Внесённые ошибки пойманы* | 30 из 30 (100%): единицы 8/8, числа 8/8, несуществующие 7/7, опечатки 7/7 | |
| Время на запрос, p50 / p95 | 51–54 / 102–104 мс (2 прогона) | 48–54 / 78–93 мс |
| «Сломай решение» (qa/break.csv) | 32 из 32 (100%), 0 ответов 500, 0 ошибок JS | |

\* набор известен разработчикам — оценка оптимистичная. По категориям отложенного набора (код 1-й / статус): мебель 15/15, 15/15; инструменты 15/15, 14/15; одежда 13/15, 14/15.

Подробности: `qa/summary.md`; воспроизвести: `python qa/run_eval.py`, `python qa/run_eval.py --cases=holdout.csv`, `python qa/run_holdout.py`, `python qa/run_break.py --base http://127.0.0.1:<порт>`.
