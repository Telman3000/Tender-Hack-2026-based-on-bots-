# QA eval — origin/main 0978986 + feature/core d341012 (fast-forward)

Run: 2026-10-10 12:16 MSK. Fresh clone, README Windows steps followed literally: venv + pip 41 s,
`build_index` 117 s, 3391 KTRU positions (furniture 355, clothing 1522, tools 1514), 72 753 allowed-value rows, catalog.db 120 MB.
pytest 35 passed. 45 cases, domain_hint on, two runs per variant identical (deterministic).

Status scoring: clean+ok only with correct top-1; clean+ambiguous/need_more only if expected group in top-3;
incomplete: need_more|ambiguous; error: anything except ok.

## Before GT change (cases.csv as of 0139aa0)
| slice | n | top-1 | top-3 | group | status | false-confident (err) | ok-but-wrong-code | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 45 | 98% | 100% | 100% | 98% | 0% | 0% | 55 | 155 | 219 |
| category=clothing | 15 | 93% | 100% | 100% | 100% | 0% | 0% | 57 | 94 | 126 |
| category=furniture | 15 | 100% | 100% | 100% | 93% | 0% | 0% | 38 | 56 | 57 |
| category=tools | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 58 | 179 | 219 |
| type=clean | 15 | 100% | 100% | 100% | 93% | - | 0% | 57 | 115 | 126 |
| type=error | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 58 | 179 | 219 |
| type=incomplete | 15 | 93% | 100% | 100% | 100% | - | 0% | 41 | 55 | 55 |

## After GT change
| slice | n | top-1 | top-3 | group | status | false-confident (err) | ok-but-wrong-code | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 45 | 98% | 100% | 100% | 100% | 0% | 0% | 51 | 116 | 203 |
| category=clothing | 15 | 93% | 100% | 100% | 100% | 0% | 0% | 57 | 94 | 125 |
| category=furniture | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 38 | 56 | 57 |
| category=tools | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 51 | 116 | 203 |
| type=clean | 15 | 100% | 100% | 100% | 100% | - | 0% | 57 | 112 | 125 |
| type=error | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 55 | 116 | 203 |
| type=incomplete | 15 | 93% | 100% | 100% | 100% | - | 0% | 41 | 52 | 59 |

GT change (verified against ACTIVE KTRU XML): FU18 — need_more also allowed. Top code 31.01.11.122-00000001
«Шкаф архивный металлический» is ACTIVE and requires «Тип дверей шкафа», which is absent from the query.
Office desk cases (FU16/FU26/FU28/FU30) now return 31.01.10.000-00000004 «Стол письменный» (ACTIVE); expected group 31.01 unchanged.

Remaining top-1 miss: CL08 «Халат размер 48» (incomplete) -> 14.14.10.000 «Халат» (household), 14.12.30.130 is 2nd.

UI: smoke (10 API cases, no 500s, no JS errors), ui_accept (edit sync, reset to 750, «Товар не распознан») and the no-reload demo
sequence FU19 -> TO37 -> TO42 all pass.
