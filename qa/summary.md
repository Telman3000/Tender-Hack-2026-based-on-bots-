# QA eval — origin/main 9475297 + feature/core 1b31f4e + feature/ui 4f7f36a (local merge 1f25573)

Run: 2026-10-10 11:09 MSK. Fresh clone, fresh venv (Python 3.11.9), `pip install -r requirements.txt` (29 s),
index built exactly per README (`python -m scripts.build_index --materials <Kazan2026_unzipped>`, no flags): 71 s, 3391 KTRU positions
(furniture 355, clothing 1522, tools 1514). pytest 29 passed. 45 cases, domain_hint on, two runs identical (deterministic).

Status scoring: clean+ok counts only with correct top-1; clean+ambiguous/need_more only if expected group in top-3;
incomplete: need_more|ambiguous; error: anything except ok.

| slice | n | top-1 | top-3 | group | status | false-confident (err) | ok-but-wrong-code | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 45 | 96% | 100% | 100% | 98% | 0% | 0% | 48 | 99 | 110 |
| category=clothing | 15 | 93% | 100% | 100% | 100% | 0% | 0% | 58 | 99 | 110 |
| category=furniture | 15 | 93% | 100% | 100% | 93% | 0% | 0% | 42 | 54 | 59 |
| category=tools | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 48 | 66 | 100 |
| type=clean | 15 | 100% | 100% | 100% | 93% | - | 0% | 59 | 100 | 110 |
| type=error | 15 | 93% | 100% | 100% | 100% | 0% | 0% | 56 | 66 | 67 |
| type=incomplete | 15 | 93% | 100% | 100% | 100% | - | 0% | 42 | 54 | 56 |

Previous: feature/core 08c5d17 — top-1 93%, top-3 100%, status 89%, p50 57 ms (same cases.csv).

UI acceptance (qa/ui_accept.py): edit 750->900 syncs table/request/response/text; reset restores table, text and result to 750;
not_found shown as «Товар не распознан»; no JS console errors; favicon served as /static/favicon.svg (bare /favicon.ico still 404, not requested by the page).

## Failures (top-3 miss or wrong status)

| id | type | query | expected | got top3 | status | domain |
|---|---|---|---|---|---|---|
| FU18 | clean | Шкаф металлический для документов сварной высота 660 мм ширина 420 мм глубина 350 мм масса 19 кг 2 полки | 31.01 / ok|ambiguous | 31.01.11.121-00000003 31.01.11.121-00000005 31.01.11.122-00000001 | need_more | furniture |
