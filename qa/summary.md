# QA eval — main@ab39ee1, 2026-10-11 01:09

Cases: 45; domain_hint=on. Status accepted sets per case are in cases.csv (clean: ok counts only with correct top-1; ambiguous/need_more only if expected group is in top-3; incomplete: need_more|ambiguous; error: anything except ok).

| slice | n | top-1 | top-3 | group | status | false-confident (err) | ok-but-wrong-code | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 45 | 98% | 100% | 100% | 100% | 0% | 0% | 27 | 70 | 155 |
| category=clothing | 15 | 93% | 100% | 100% | 100% | 0% | 0% | 32 | 70 | 155 |
| category=furniture | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 21 | 30 | 30 |
| category=tools | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 26 | 36 | 147 |
| type=clean | 15 | 100% | 100% | 100% | 100% | - | 0% | 32 | 147 | 155 |
| type=error | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 29 | 35 | 36 |
| type=incomplete | 15 | 93% | 100% | 100% | 100% | - | 0% | 22 | 31 | 32 |

## Failures (top-3 miss or wrong status)

| id | type | query | expected | got top3 | status | domain |
|---|---|---|---|---|---|---|
