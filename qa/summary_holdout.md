# QA eval — main@ab39ee1, 2026-10-11 01:09

Cases: 45; domain_hint=on. Status accepted sets per case are in cases.csv (clean: ok counts only with correct top-1; ambiguous/need_more only if expected group is in top-3; incomplete: need_more|ambiguous; error: anything except ok).

| slice | n | top-1 | top-3 | group | status | false-confident (err) | ok-but-wrong-code | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 45 | 96% | 98% | 100% | 96% | - | 0% | 25 | 49 | 157 |
| category=clothing | 15 | 87% | 93% | 100% | 93% | - | 0% | 30 | 48 | 157 |
| category=furniture | 15 | 100% | 100% | 100% | 100% | - | 0% | 21 | 30 | 32 |
| category=tools | 15 | 100% | 100% | 100% | 93% | - | 0% | 28 | 49 | 128 |
| type=clean | 27 | 96% | 96% | 100% | 93% | - | 0% | 30 | 128 | 157 |
| type=incomplete | 18 | 94% | 100% | 100% | 100% | - | 0% | 23 | 26 | 30 |

## Failures (top-3 miss or wrong status)

| id | type | query | expected | got top3 | status | domain |
|---|---|---|---|---|---|---|
| H09 | clean | Сапоги резиновые с защитным подноском (размер 44) Вид крепления подошвы литьевой Вид средства защиты ног Сапоги Вид товаров Одежда | 15.20.11.113 / ok|ambiguous|need_more | 15.20.31.000-00000003 15.20.32.126-00000001 15.20.32.121-00000001 | need_more | clothing |
| H31 | clean | Электролобзик Graphite 58G071 Быстрозажимное крепление пилки Нет Вес 2.1 г Высота 225.00000 мм | 28.24.11.000 / ok|ambiguous|need_more | 28.24.11.000-00000004 28.24.11.000-00000005 28.24.11.000-00000006 | error | tools |
