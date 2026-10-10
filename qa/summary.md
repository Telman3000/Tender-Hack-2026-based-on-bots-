# QA eval — origin/main bf6c60e + feature/core d8b6019 (fast-forward)

Run: 2026-10-10 12:35 MSK. Fresh clone, README Windows steps: venv + pip 36 s, `build_index` 100 s, 3391 KTRU positions.
pytest 40 passed (1 Starlette deprecation warning, documented). 45 cases, domain_hint on, two runs identical (deterministic).
cases.csv unchanged since ee24992.

Status scoring: clean+ok only with correct top-1; clean+ambiguous/need_more only if expected group in top-3;
incomplete: need_more|ambiguous; error: anything except ok.

| slice | n | top-1 | top-3 | group | status | false-confident (err) | ok-but-wrong-code | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 45 | 98% | 100% | 100% | 100% | 0% | 0% | 66 | 134 | 228 |
| category=clothing | 15 | 93% | 100% | 100% | 100% | 0% | 0% | 56 | 97 | 132 |
| category=furniture | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 47 | 91 | 134 |
| category=tools | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 98 | 177 | 228 |
| type=clean | 15 | 100% | 100% | 100% | 100% | - | 0% | 71 | 132 | 228 |
| type=error | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 67 | 134 | 177 |
| type=incomplete | 15 | 93% | 100% | 100% | 100% | - | 0% | 48 | 86 | 100 |

Second run: p50 56 / p95 113 / max 124 ms.

UI: smoke (no 500s, no JS errors), ui_accept (edit sync, reset to 750, «Товар не распознан») and the no-reload demo sequence
FU19 -> TO37 -> TO42 -> 270 мм pass with the documented statuses and funnels. New in d8b6019: optional KTRU characteristics are added
as empty table rows (e.g. FU19 +3 rows, TO37 +2), unitless dimensions get «принято … мм» warnings.

## Failures (top-3 miss or wrong status)

| id | type | query | expected | got top3 | status | domain |
|---|---|---|---|---|---|---|


# Holdout and error sets — origin/main 0c9b8c7 (includes feature/core d8b6019)

Run: 2026-10-10 12:41 MSK. Ground truth fixed and pushed BEFORE the run: holdout.csv in 0ebf4b8, errors.csv in 09e4eef; not edited after.

## Holdout (qa/holdout.csv, 45 new portal items, 27 clean / 18 incomplete; different portal items from the 45 dev cases, mostly different product types)
GT = OKPD2 prefix of ACTIVE KTRU positions with the matching name (ktru XML). Two runs identical.

| slice | top-1 | top-3 | status |
|---|---|---|---|
| all | 43 из 45 | 44 из 45 | 43 из 45 |
| clothing | 13 из 15 | 14 из 15 | 13 из 15 |
| furniture | 15 из 15 | 15 из 15 | 15 из 15 |
| tools | 15 из 15 | 15 из 15 | 15 из 15 |
| clean | 26 из 27 | 26 из 27 | 25 из 27 |
| incomplete | 17 из 18 | 18 из 18 | 18 из 18 |

Latency p50 62 / p95 113 / max 181 ms (run 2: 44 / 99 / 122).
Failures: H02 «Брюки» -> 14.13.10 first (expected 14.13.12.140 is 2nd); H09 «Сапоги резиновые с защитным подноском» -> 15.20.31/32
(protective footwear; GT 15.20.11.113 «Сапоги резиновые формовые» is arguably too narrow, but GT is not changed after the run);
H12 «Перчатки трикотажные … размер 11» -> status error (glove size 11 checked against clothing size range 18–80).
Note: need_more on clean holdout cases is accepted when the expected group is in top-3 (required characteristics not checked per case).

## Synthetic errors (qa/errors.csv, 30 cases on real item types)
Detection: 19 из 30 — unit 8 из 8, unrealistic 7 из 8, typo 4 из 7, nonexistent value 0 из 7.
Misses: E11 width 0.5 мм for a cabinet (no lower-bound check); E17–E23 values not in the KTRU list written as free text
(«вид материала обивки спинки бетон», «тип исполнения Z», …) — the multi-word characteristic name is not parsed, the value is
dropped and only «не заполнена обязательная характеристика» is reported; E28 «производственый», E29 «Шуруповерд», E30 «Малоток» not flagged.

## False alarms on clean cases (clean of cases.csv + clean of holdout.csv)
Strict (status error or error-severity issue): 1 из 42 — H12 glove size 11.
Soft (any warning other than missing/ambiguous): 2 из 42 — H12, H27 (unitless 1100х250х1000 -> «принято … мм», by design).
Details: qa/results_holdout.csv, qa/errors_results.csv, qa/false_alarms.csv. Scripts: qa/make_holdout.py, qa/run_holdout.py,
qa/run_eval.py --cases=holdout.csv.


# Acceptance feature/core d35047b (on origin/main 0c9b8c7, fast-forward, no conflicts) — 2026-10-10 12:57 MSK

pytest 58 passed. All runs done twice, identical results.

| set | previous (0c9b8c7) | d35047b |
|---|---|---|
| dev 45 top-1 / top-3 / status | 96% / 98% / 100% (summary 98%) | 98% / 100% / 100% (CL08 top-1 miss) |
| holdout top-1 / top-3 / status | 43 / 44 / 43 из 45 | 43 / 44 / **40** из 45 |
| errors detection | 19 из 30 | **30 из 30** (unit 8/8, unrealistic 8/8, nonexistent 7/7, typo 7/7) |
| false alarms clean strict | 1 из 42 (H12) | **4 из 42** (H04, H17, H27, H31) |
| false alarms clean soft | 2 из 42 (H12, H27) | 2 из 42 (H23, H27) |

Holdout by category, d35047b: clothing 13/14/13 из 15, furniture 15/15/13 из 15, tools 15/15/14 из 15.

Strict flags, judged one by one:
- H04 «Фартук мед. клеенка Вид защиты Защита от общих производственных загрязнений…» -> not_allowed «Вид защиты» = «защита».
  FALSE: only the first word was taken as the value; the real value is not in this position's list, but the error names a value the user never wrote.
- H17 «Диван … Вид материала наполнителя Высокоэластичный поролон» -> not_allowed «Наполнитель» = «высокоэластичный поролон» (allowed: spring block types / Беспружинный).
  FALSE: filler material was mapped onto the KTRU spring-type characteristic; foam = «Беспружинный».
- H27 «Витрина … Вид материала каркаса алюминиевый профиль» -> not_allowed (allowed: Алюминий, Сталь нержавеющая).
  FALSE as an error: «алюминиевый профиль» = Алюминий; it should be an autofix/warning, not severity=error.
- H31 «Электролобзик Graphite 58G071 … Вес 2.1 г» -> mismatch «Вес 2.1 г нереалистично мало», suggestion 2.1 кг.
  REAL: the portal card really has a unit error.
Regression: real false alarms grew from 1 (H12, now fixed) to 3 (H04, H17, H27), plus soft H23 typo «поставки»->«подставки» («Вид поставки» is a correct word).
Holdout status 43 -> 40 is entirely these 3 false errors.

Blindness: no strings from errors.csv/holdout.csv in app/ code (only a docstring example «производственый», «Шуруповерд»; tests use similar
phrases such as «Молоток тип ювелирный»). The changes are general rules (parsing «name value», size range per item type, lower limits,
typo check on all words), but clearly made in response to the published misses, so errors.csv is no longer blind (30/30 is optimistic).

docs/api.md vs real response («Ключ гаечный 17х19 мм длина 27 см цвет чорный», port 8809): top-level fields, characteristics/issues/narrowing
fields and types match; the example fragment matches exactly. Gaps: empty text -> HTTP 422 is not documented (only bad domain_hint is);
characteristics[].span covers name+value ([22,33]) while corrections[].span covers only the value ([28,33]), which is not explained.
scripts/load_test.py (50/50, 1 worker): 50/50 ok, p50 3.57 s, p95 4.92 s, max 4.95 s, 10.1 req/s — matches README (4.2/5.7 s, 8.7 req/s).
RSS columns print null: psutil is optional and not in requirements, so README RSS numbers cannot be reproduced without `pip install psutil`.


# Acceptance feature/ui db881e8 on origin/main 0c9b8c7 + core d35047b (local merge feb1466, no conflicts) — 2026-10-10 13:04 MSK

Real browser (headless Edge, Playwright), port 8810, screenshots in wt-qa/_out/ui-db881e8/. pytest 58 passed. JS console errors: none.
- Highlighting: marks use issue spans (value only): «27 м» [30,34], «бетон» [43,48], with the error text as a tooltip. Characteristic spans cover name+value
  («длина 27 м» [24,34]) and are not highlighted, which is correct. After typing «Новый » before the text the mark still sits on «27 м» (no drift).
- «Было → стало»: TO42 «единицы · Длина разводного ключа: 27 м → 27000 мм»; wrench «27 см → 270 мм». FU19: no block (as docs say for core).
- Badges «Код»/«Карточка» and the completeness line are correct in all demo states; optional steps are grey (rgb 138,148,166) with «(необязательно)».
- Demo FU19 -> TO37 -> TO42 -> 270 without reload matches the updated demo_script.md, except: FU19 after editing shows «4/7 необязательных»
  (two new optional rows appear; the script only mentions 4/5 before editing); TO42 «Исправьте «длина»: 27 мм» is shown as optional/grey (documented, but it is a
  severity=error fix — UX bug in core next_steps_detail).
- ui_accept: edit 750->900 recalculates, reset brings 750 back (table/text/result), not_found label ok. /static/favicon.svg 200 (direct /favicon.ico 404, no console error).
- smoke: 10/10 API 200, UI queries render, edit updates text.

Presentation check (presentation.pptx slide 6 = presentation_7min.pptx slide 8 unless noted), compared with d35047b numbers:
- «Статус верный (отложенный) 43/45 · 96%» -> 40/45 (89%) on d35047b (43/45 was 0c9b8c7).
- «Мебель / инструменты / одежда 15/15 · 15/15 · 13/15» sits under the status row but is top-1 by category; status by category on d35047b is 13 · 14 · 13.
- «Ложные тревоги на чистых 1/42» -> 4/42 (3 genuine false: H04, H17, H27).
- «p95 ~100–115 мс» -> 99–164 ms over the four d35047b runs.
- «Чистая сборка индекса 71 с» -> last jury build 100 s (71 s was an older build).
- «воронка N → M → 1» -> funnel ends with a group of 2–3 variations (demo FU19 355→2, TO37 1514→3→…→2).
- 7min slide 9 «пойманы 19/30 … несуществующие 0/7» and plan item «ловить несуществующие значения — следующий шаг» -> 30/30 on d35047b (post-tuning, optimistic); feature is implemented.
- Header «Цифры на текущей версии · main 0c9b8c7» -> true for 0c9b8c7 but outdated once core d35047b is merged.
- Correct: top-1/top-3 dev 44/45, 45/45; holdout 43/45, 44/45; median ~50 ms; ≈600 ms debounce (DEBOUNCE_MS = 600); «355 → 2»; «27 м → 27 мм».
- Not on slides: pytest 58, 3391 positions, load test 50 parallel p50 3.57 s.


# Acceptance core 9e6d6a9 + ui 8c1c598 on origin/main 0c9b8c7 (local merge d15f95f, no conflicts) — 2026-10-10 13:13 MSK

pytest 62 passed. Two runs each, identical results.

| set | d35047b | 9e6d6a9 |
|---|---|---|
| dev 45 top-1 / top-3 / status | 44 / 45 / 45 | 44 / 45 / 45 (CL08 top-1 miss) |
| holdout top-1 / top-3 / status | 43 / 44 / 40 | 43 / 44 / **43** из 45 |
| holdout by category (top-1/top-3/status) | — | clothing 13/14/14, furniture 15/15/15, tools 15/15/14 |
| errors | 30 из 30 | 30 из 30 (unit 8, unrealistic 8, nonexistent 7, typo 7) — optimistic, tuned after seeing the set |
| false alarms strict | 4 из 42 | **1 из 42** (H31) |
| false alarms soft | 2 из 42 | 3 из 42 (H04, H17, H27) |
| latency p50 / p95 (dev, 2 runs) | — | 54/186, 55/169 ms; holdout 53/158, 48/173 ms |

Flagged clean cases:
- H31 «Электролобзик … Вес 2.1 г» error: GENUINE (the portal card's weight unit is wrong). Counts as a holdout status miss only because GT expected a clean card.
- H04 warning «Вид защиты» = «защита от общих производственных загрязнений» not in this position (exists in others): GENUINE mismatch with the chosen code; the full value is now parsed correctly.
- H17 warning «Наполнитель» = «высокоэластичный поролон» (mapping marked uncertain): FALSE (filler material mapped onto spring type), downgraded to a warning.
- H27 unitless 1100х250х1000 «принято мм»: by design, not an error. «алюминиевый профиль» now matches Алюминий.
Holdout misses: H02 (Брюки, expected group 2nd), H09, H31.
H09 «Сапоги резиновые с защитным подноском»: engine top-1 15.20.31.000-00000003 «Обувь с защитным металлическим подноском» (ACTIVE) fits the explicit protective toe cap;
GT 15.20.11.113 «Сапоги резиновые формовые» also fits (rubber moulded boots). The GT is too narrow; the engine's top-1 is defensible (the other two in top-3,
vibration-proof/dielectric, do not fit). GT not edited.
Hacks: no holdout/errors strings in app code. New COMMON_WORDS list (config.py) contains «поставки», which fixes H23; it is a generic list of procurement words, not a case string.

UI (headless Edge, port 8811, screenshots wt-qa/_out/ui-9e6d6a9/): TO42 «Исправьте «длина»: 27 мм» is now in the required list (not grey).
MANUAL_CHECK 5-minute steps: 1 open/no console errors PASS; 2 TO42 highlight/corrections/badges PASS; 3 270 мм + Тип исполнения B -> «Карточка: заполнена» PASS;
4 «Ключ» required 1, optional grey PASS; 5 desk 750->900->reset 750 PASS; 6 chair «бетон» error + highlight PASS; 7 pytest PASS (62). JS errors: none.


# Final metrics on main 7aa9939 — 2026-10-10 19:05 MSK

| Метрика | Основной набор (45) | Отложенный набор (45) |
|---|---|---|
| Код КТРУ на 1-м месте | 44 из 45 (98%) | 43 из 45 (96%) |
| Код в топ-3 | 45 из 45 (100%) | 44 из 45 (98%) |
| Статус верный | 45 из 45 (100%) | 43 из 45 (96%) |
| Ложные тревоги на чистых (ошибка) | 1 из 42 (2%) — H31, в карточке реальная ошибка (лобзик 2,1 г) | |
| Предупреждения на чистых (мягкие) | 3 из 42 (7%) | |
| Внесённые ошибки пойманы* | 30 из 30 (100%): единицы 8/8, числа 8/8, несуществующие 7/7, опечатки 7/7 | |
| Время на запрос, p50 / p95 | 53–98 / 126–194 мс (2 прогона) | 49–60 / 102–138 мс |
| «Сломай решение» (qa/break.csv) | 28 из 32 (88%), 0 ответов 500, 0 ошибок JS | |

\* набор известен разработчикам — оценка оптимистичная. По категориям отложенного набора (код 1-й / статус): мебель 15/15, 15/15; инструменты 15/15, 14/15; одежда 13/15, 14/15.

## «Сломай решение» (qa/break.csv, qa/run_break.py; API on port 8814 + headless Edge for 14 key cases)
API: 28 из 32 PASS, no HTTP 500. Browser: 14 из 14 without JS errors, alerts or injected nodes.
FAIL:
- B01/B02 «Ключ гаечный разводной мощность 100 (Вт)»: «Мощность 100 Вт» accepted as a portal characteristic of a hand wrench, no warning.
- B16 synonyms: «вес 500 г» -> portal «Масса», «масса 500 г» -> KTRU «Масса молотка» (same code, different characteristic).
- B27 «Стол письменный высота -750 мм»: the negative value is silently dropped (no row, no issue); 0 and huge values are flagged.
Notes (PASS on safety, recognition bugs): B23/B24 an HTML tag before the text («<script>… стул офисный») -> not_found, product_guess «<script>alert»;
markup is escaped in the UI. Empty text: API 422 (B12), whitespace -> not_found; in the UI an empty submit sends no request.
No CSV/batch endpoint or UI exists; 100 rows (45 dev + 45 holdout + 10 broken) through /api/analyze: 9.9 s sequential, 5.9 s with 4 parallel, codes 200/422 only.
Very long text: 9.8k chars 130 ms, 98k chars 0.6 s.


# Acceptance feature/ui 5dc532a (with dad33b5) on main 7aa9939 — 2026-10-10 20:16 MSK

Fast-forward merge, no conflicts; diff touches only frontend/ (app.js, index.html, styles.css), docs/demo_batch.csv and docs/screens — no app/ changes.
pytest 62 passed; dev 44/45 · 45/45 · 45/45, holdout 43/45 · 44/45 · 43/45 (unchanged). Real browser: headless Edge, port 8815; screenshots wt-qa/_out/ui-5dc532a/.
- smoke, ui_accept (edit 750->900 syncs text, reset -> 750, not_found label), MANUAL_CHECK 7 steps, demo FU19->TO37->TO42->270: PASS, no JS errors.
  (ui_accept now finds the «Высота» row by name: with the new KTRU->portal->new order the first row can be a select.)
- Empty input: «Проверить» with empty or whitespace text sends no request and shows «Введите описание товара» with an example; the old result is cleared.
- «Допишите ещё n (обязательных: k)»: k equals missing required from the API in 6/6 queries; n = required + empty optional.
- Batch tab (qa/ui_batch.py, qa/make_batch.py, qa/batch100.csv = 45 dev + 45 holdout + 10 broken + blank lines):
  demo_batch.csv 11 rows 1.9 s; batch100 utf-8 «;» with header 6.9 s; cp1251 «,» quoted, header «name» 6.3 s; utf-8 BOM, no header 6.2 s.
  100/100 rows each, every row's code equals a single /api/analyze call, export CSV has header + all rows, row click opens it in the editor,
  no alerts or injected <script>/<img> (XSS escaped), blank lines skipped, header variants detected.
Bugs:
1. Every batch run logs 2 console errors «Failed to load resource: 404» — the UI probes /api/analyze/batch?stream=1 and /api/analyze/batch,
   which core does not have, then falls back to per-row calls (4 parallel). Works, but a jury opening DevTools sees red errors.
2. Narrow width 420 px: page scrolls horizontally (scrollWidth 474 on the single view, 992 on the batch tab because of the wide table). Fine at 1280.
3. A description containing «;» in a file that uses «;» is cut at the first «;» unless quoted (by design: only the first column is read).


# Acceptance feature/ui c3cddec (+0d97c90) on main af74a6b — 2026-10-10 20:31 MSK

Fast-forward, no conflicts. No app/ changes (main af74a6b vs 7aa9939: frontend, docs, qa only; ui: frontend, docs, frontend/tests). Index not rebuilt (core unchanged).
pytest 62; dev 44/45 · 45/45 · 45/45; holdout 43/45 · 44/45 · 43/45; break 28/32 (same 4 core FAILs: B01/B02, B16, B27); API batch 100 rows 6.6 s sequential / 3.8 s 4-parallel.
Fixes verified (headless Edge, port 8816):
- Batch: no HTTP >= 400 and no console errors (one quiet GET /openapi.json, falls back to per-row /api/analyze).
- 420 px: scrollWidth = 420 on both tabs (was 474 / 992); 1280 unchanged.
- CSV: unquoted «;» or «,» inside a one-column file is kept as the whole description; header «Наименование;Количество» / «name,qty»
  picks the name column; quoted «,» inside a field is kept.
Regression: ui_accept PASS, MANUAL_CHECK 6/6 + pytest, ui_batch: demo_batch 11 rows 0.6 s, batch100 (utf-8 ;) 4.3 s, cp1251 «,» 4.5 s, 100/100 rows equal
to single /api/analyze, export ok, XSS escaped, no JS errors.
New demo_script.md walked literally: all codes, funnels, badges, counters, highlight, chip «B», batch summary (8/2/1, 4/6/1) match. Mismatches:
- (a) line 24: «Было → стало … ткань → Текстиль» is not shown for FU19 on main (no correction is reported).
- (b) line 39: block text is «27 м → 27000 мм», not «длина 27 м → 27000 мм».
presentation_final.pptx: every number matches qa/metrics_slide.md and the batch run. Nit: slide 3 «Ответ < 0,1 с» — true for the median, p95 is 0.1–0.2 s.

## Приёмка core 24411af + ui 4d6ae93 (поверх main c6a89cd), 2026-10-10 21:26 МСК

Временная сборка acc3 = c6a89cd + 24411af + 4d6ae93, без конфликтов, не пушилась. Индекс не пересобирался (код сборки не менялся), 3030 позиций.

| Набор | Код топ-1 | Код в топ-3 | Статус |
|---|---|---|---|
| основной (45) | 44 из 45 (98%) | 45 из 45 (100%) | 45 из 45 (100%) |
| отложенный (45) | 43 из 45 (96%) | 44 из 45 (98%) | 43 из 45 (96%) |

- pytest: 109 passed
- Синтетические ошибки найдены: 30 из 30 (единицы 8/8, нереалистичные 8/8, несуществующие 7/7, опечатки 7/7). Оценка оптимистичная, ядро настраивали на этот набор.
- Ложные срабатывания на чистых, строгие: 1 из 42 (H31, ошибка в самих данных: 2,1 г); мягкие: 3 из 42 (H04, H17, H27). TO35 ушёл, новых нет.
- Набор «сломай решение»: 32 из 32, 0 ответов 500, 0 ошибок JS. Ноутбук -> out_of_scope.
- Время на запрос p50/p95: основной 51–54/102–104 мс, отложенный 48–54/78–93 мс (2 прогона).
- Пакет 100 строк: API batch 3,85 с, stream 4,13 с, CSV 3,6–4,1 с; во вкладке UI 3,3–3,4 с, 0 расхождений с одиночным анализом. 13 строк из demo_batch: 0,48 с.
- UI: fill=null (Молоток отбойный 1510 Вт) показывается без «0 из 0» и без ошибок JS; MANUAL_CHECK 6/6 PASS; ui_accept без ошибок JS; при 420 px горизонтальной прокрутки нет.
- Документация: README:94/199 «3391» -> надо 3030 (строка 193 уже 3030); README:240 «28 из 32» -> 32 из 32; в деке слайд 3 «13 строк ≈1,3 с» (измерено 0,48 с), слайд 6 ссылается на main 7aa9939.
