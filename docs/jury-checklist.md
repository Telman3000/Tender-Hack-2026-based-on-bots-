# Чек-лист для жюри: заявлено vs проверено

Дата проверки: **2026-10-11** (облачный прогон перед предзащитой).  
Коммит: **3532572** (ветка `main` после слияния PR по core / UI / QA / docs).  
Окружение: Python 3.12, Linux, `data/processed/catalog.db` собран из материалов «Казань 2026» (Yandex Disk).

Как воспроизвести локально — команды в конце каждого блока.

---

## 1. Ядро: только актуальный КТРУ, новейшая версия

| Заявление | Факт | Как проверить |
|---|---|---|
| В индекс попадают только `all_actual`, не `not-actual` | Да | `pytest tests/test_core_predefense.py::test_not_actual_files_never_used` |
| Из нескольких версий одной позиции — самая новая (`version`, `updateDate`) | Да | `test_newest_version_wins_regardless_of_order` |
| TERMINATED/INACTIVE не попадают в индекс | Да | `test_inactive_positions_skipped` |
| Полные дубликаты сводятся к одной, новейшей записи | Да | `test_identical_positions_keep_newest`; в логе сборки `identical duplicates removed: 361` |
| Итого **3030** позиций в 3 доменах | Да | `python -m scripts.build_index --materials _materials` → `"ktru": 3030` |

---

## 2. Абсурдные характеристики, синонимы, порядок, вне категории

| Заявление | Факт | Как проверить |
|---|---|---|
| «Мощность 100» у гаечного ключа — **предупреждение**, не «Новая» | Да | `test_absurd_property_is_suspicious_not_new` |
| Мощность у дрели/перфоратора — не подозрительная | Да | `test_drill_power_is_not_suspicious`, `test_power_tool_power_not_suspicious` |
| вес/масса → одна каноническая характеристика | Да | `test_weight_and_mass_same_characteristic`, `test_uniform_name` |
| Порядок строк: **КТРУ → Портал → Новая** | Да | `test_order_ktru_portal_new` |
| Товар 4-й категории: «не наша категория», без падения | Да | `test_out_of_scope`; API `POST /api/analyze` с «Хлеб…», «Ноутбук…» → `out_of_scope: true` |
| Вопрос пользователю — только если нельзя решить автоматически | Да | `test_question_only_when_needed` |

---

## 3. Недостающие характеристики (ядро + UI)

| Заявление | Факт | Как проверить |
|---|---|---|
| Сравнение с **всеми** характеристиками выбранного кода КТРУ | Да | `test_full_missing_list_required_first_with_allowed` |
| Блок «Допишите ещё n характеристик», обязательные первыми | Да | UI `#fillBlock`; скрин `docs/screens/fill_block.png` |
| Счётчик «N из M» / «Заполнено N из M» | Да | поле `fill` в JSON; UI `#fillCounter` |
| One-click из допустимых значений КТРУ | Да | чипы `.chip[data-fill]` в UI |

---

## 4. Загрузка CSV

| Заявление | Факт | Как проверить |
|---|---|---|
| Кнопка и вкладка «Пакетная проверка (CSV)» | Да | http://127.0.0.1:8000/ → вкладка CSV |
| Один столбец наименований, UTF-8/cp1251 | Да | `pytest tests/test_batch.py` |
| Построчный результат + сводка + экспорт CSV | Да | UI `#exportCsv`; `docs/demo_batch.csv` |
| **100 строк ~1–10 с** (не нейросеть, локально) | Да | `qa/run_break.py`: batch 100 rows **1.9–2.6 s** (1–4 parallel) |

---

## 5. Метрики QA (не выдуманы)

| Метрика | Основной (45) | Holdout (45) | Источник |
|---|---|---|---|
| Top-1 код КТРУ | 44/45 (98%) | 43/45 (96%) | `python qa/run_eval.py` → `qa/summary.md` |
| Top-3 | 45/45 (100%) | 44/45 (98%) | то же |
| Статус | 45/45 (100%) | 43/45 (96%) | то же |
| Внесённые ошибки пойманы | 30/30 | — | `python qa/run_holdout.py` |
| Ложные **error** на чистых | 1/42 (H31 — реальный вес 2,1 г) | — | `run_holdout.py` |
| Мягкие предупреждения | 3/42 | — | `run_holdout.py` |
| p50 / p95 (eval) | **27 / 70 ms** | **25 / 49 ms** | `qa/summary.md`, прогон 2026-10-11 |
| «Сломай решение» | **32/32**, 0×500 | — | `python qa/run_break.py --base http://127.0.0.1:8000` |
| pytest | **125/125** | — | `python -m pytest -q` |

Слайд для презентации: [`qa/metrics_slide.md`](../qa/metrics_slide.md).

---

## 6. Скорость «< 0,1 с»

| Что измеряем | Результат | Примечание |
|---|---|---|
| Время **движка** (`debug.elapsed_ms`), 150 замеров | p50 **~29 ms**, p95 **~33 ms**, 99% < 100 ms | `python scripts/measure_latency.py` |
| Полный HTTP-запрос (eval, 45+45 кейсов) | p50 **27–32 ms**, p95 **70–155 ms** | сеть + JSON; см. `qa/run_eval.py` |
| UI debounce | 600 ms | намеренная задержка ввода, не время сервера |

**Честная формулировка для жюри:** обработка одного запроса на сервере — **десятки миллисекунд** (медиана **< 0,1 с**); в браузере с debounce и первым прогревом может быть **0,1–0,2 с**.

---

## 7. UI «Портал поставщиков»

| Заявление | Факт | Как проверить |
|---|---|---|
| Цвета/шрифты по UI-kit (#264B82, #DB2B21, Open Sans) | Да | `frontend/styles.css` (комментарий Figma UI-kit) |
| Шапка, вкладки, красная primary-кнопка | Да | открыть `/` |

---

## 8. Офлайн, без нейросетей

| Заявление | Факт | Как проверить |
|---|---|---|
| Нет вызовов OpenAI/Gemini/Claude и внешних LLM API | Да | поиск по репо: нет SDK LLM; `requirements.txt` |
| Работа без интернета после сборки `catalog.db` | Да | отключить сеть, запустить uvicorn — анализ работает |
| Каждый шаг сужения с `reason` в `narrowing[]` | Да | ответ API / UI «Воронка» |

---

## 9. Презентация и демо

| Артефакт | Путь |
|---|---|
| Markdown (7 слайдов, ~5 мин) | [`docs/presentation.md`](presentation.md) |
| HTML-слайды (браузер, ~3–5 мин) | [`docs/presentation/index.html`](presentation/index.html) |
| PowerPoint (финал) | `docs/presentation_final.pptx` |
| Сценарий демо + CSV | [`docs/demo_script.md`](demo_script.md), [`docs/demo_batch.csv`](demo_batch.csv) |
| Ответы на вопросы | [`docs/jury_qa.md`](jury_qa.md) |

---

## Быстрый прогон перед выходом на защиту

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# materials → _materials/, затем:
python -m scripts.build_index --materials _materials
python -m pytest -q
python qa/run_eval.py && python qa/run_eval.py --cases=holdout.csv --suffix=_holdout
python qa/run_holdout.py
uvicorn app.main:app --port 8000 &
python qa/run_break.py --base http://127.0.0.1:8000
python scripts/measure_latency.py
```

`catalog.db` и `_materials/` в git **не** коммитятся (см. `.gitignore`).
