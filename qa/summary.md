# QA eval — nikari/ktru-improvements@bf6c60e, 2026-10-10 13:33

Cases: 55; domain_hint=on. Status accepted sets per case are in cases.csv (clean: ok counts only with correct top-1; ambiguous/need_more only if expected group is in top-3; incomplete: need_more|ambiguous; error: anything except ok).

| slice | n | top-1 | top-3 | group | status | false-confident (err) | ok-but-wrong-code | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 55 | 98% | 100% | 100% | 100% | 0% | 0% | 28 | 54 | 98 |
| category=clothing | 17 | 94% | 100% | 100% | 100% | 0% | 0% | 30 | 51 | 98 |
| category=furniture | 20 | 100% | 100% | 100% | 100% | 0% | 0% | 22 | 54 | 60 |
| category=tools | 18 | 100% | 100% | 100% | 100% | 0% | 0% | 28 | 36 | 72 |
| type=clean | 16 | 100% | 100% | 100% | 100% | - | 0% | 37 | 72 | 98 |
| type=error | 21 | 100% | 100% | 100% | 100% | 0% | 0% | 25 | 33 | 37 |
| type=incomplete | 18 | 94% | 100% | 100% | 100% | - | 0% | 23 | 30 | 34 |

## Failures (top-3 miss or wrong status)

| id | type | query | expected | got top3 | status | domain |
|---|---|---|---|---|---|---|
