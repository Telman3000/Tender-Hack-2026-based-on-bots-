Основной путь — текущий разбор без модели.

Полнота короткого списка дописывается командой `python qa/run_eval.py` и печатается как k/n отдельно по clothing, furniture и tools. Ниже сохранён базовый прогон 45 кейсов.

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
