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
