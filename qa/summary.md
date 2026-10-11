# QA eval — fix/redteam-priority@988f7ea, 2026-10-11 10:13

Cases: 45; domain_hint=on. Status accepted sets per case are in cases.csv (clean: ok counts only with correct top-1; ambiguous/need_more only if expected group is in top-3; incomplete: need_more|ambiguous; error: anything except ok).

| slice | n | top-1 | top-3 | group | status | false-confident (err) | ok-but-wrong-code | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 45 | 98% | 100% | 100% | 100% | 0% | 0% | 24 | 51 | 107 |
| category=clothing | 15 | 93% | 100% | 100% | 100% | 0% | 0% | 27 | 51 | 107 |
| category=furniture | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 19 | 25 | 25 |
| category=tools | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 24 | 30 | 104 |
| type=clean | 15 | 100% | 100% | 100% | 100% | - | 0% | 28 | 104 | 107 |
| type=error | 15 | 100% | 100% | 100% | 100% | 0% | 0% | 25 | 30 | 30 |
| type=incomplete | 15 | 93% | 100% | 100% | 100% | - | 0% | 20 | 26 | 27 |

## Failures (top-3 miss or wrong status)

| id | type | query | expected | got top3 | status | domain |
|---|---|---|---|---|---|---|
