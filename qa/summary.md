# QA eval — feature/core 08c5d17 (contains main 433b64e)

Run: 2026-10-10 10:53 MSK, 45 cases, domain_hint on. Two runs each, identical top-3 and status (deterministic).
Index: `python -m scripts.build_index --materials <Kazan2026_unzipped> --ktru-files 200` -> 3391 KTRU positions.
With the README default (`--ktru-files 30`) the index has only 167 positions: top-1 drops to ~31% and 4 pytest tests fail (measured on a28b3b2).

Status scoring (tightened): clean+ok counts only with correct top-1; clean+ambiguous/need_more only if the expected group is in top-3;
incomplete: need_more|ambiguous; error: anything except ok. `ok-but-wrong-code` = status ok while top-1 is wrong.

## Before ground-truth changes (cases.csv as of 7d1cf1c)
| slice | n | top-1 | top-3 | group | status | false-confident (err) | ok-but-wrong-code | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 45 | 84% | 91% | 91% | 76% | 0% | 2% | 54 | 115 | 136 |
| category=clothing | 15 | 80% | 80% | 80% | 87% | 0% | 0% | 56 | 97 | 131 |
| category=furniture | 15 | 87% | 93% | 93% | 67% | 0% | 7% | 38 | 52 | 55 |
| category=tools | 15 | 87% | 100% | 100% | 73% | 0% | 0% | 84 | 115 | 136 |
| type=clean | 15 | 87% | 87% | 87% | 27% | - | 7% | 57 | 98 | 131 |
| type=error | 15 | 80% | 87% | 87% | 100% | 0% | 0% | 56 | 115 | 136 |
| type=incomplete | 15 | 87% | 100% | 100% | 100% | - | 0% | 43 | 84 | 88 |

## After ground-truth changes (verified against ACTIVE positions in the KTRU XML)
| slice | n | top-1 | top-3 | group | status | false-confident (err) | ok-but-wrong-code | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 45 | 93% | 100% | 100% | 89% | 0% | 0% | 57 | 154 | 186 |
| category=clothing | 15 | 100% | 100% | 100% | 93% | 0% | 0% | 57 | 97 | 110 |
| category=furniture | 15 | 93% | 100% | 100% | 87% | 0% | 0% | 42 | 56 | 61 |
| category=tools | 15 | 87% | 100% | 100% | 87% | 0% | 0% | 121 | 160 | 186 |
| type=clean | 15 | 100% | 100% | 100% | 67% | - | 0% | 57 | 110 | 154 |
| type=error | 15 | 93% | 100% | 100% | 100% | 0% | 0% | 63 | 160 | 186 |
| type=incomplete | 15 | 87% | 100% | 100% | 100% | - | 0% | 51 | 122 | 133 |

Ground-truth changes applied (each checked against ACTIVE KTRU XML):
- FU20 31.01 -> 31.09.11.120 (Стеллаж складской металлический, ACTIVE; query has metal + 100 kg/shelf)
- CL02, CL12, CL14 14.12 -> 14.13 (only ACTIVE jackets are 14.13.10.000 «Куртка зимняя из текстильных материалов»; no ACTIVE jacket in 14.12)
- CL03 14.12.2 -> 14.12.2|14.12.30.130 (14.12.20.000-0000000x «Спецодежда женская» and 14.12.30.130 «Халат производственный» both ACTIVE)
- TO35, TO45 28.24.1 -> 28.24.10.000 (only ACTIVE fit is 28.24.10.000-00000001; no ACTIVE demolition-hammer position; 25.73.30.141 «Молоток» types are hand hammers)
- need_more also allowed on 7 clean cases where a required KTRU characteristic really is absent from the text: CL03 (Обхват груди), CL05 (Вид обуви/Половой признак/Сорт), FU16 (Тип/Вид материала каркаса), FU17 (Наличие мягкого сиденья/спинки), TO31 (Тип исполнения; ACTIVE only for разводной), TO33 (Тип питания, патрон, обороты), TO35 (no ACTIVE position)

Rejected need_more on clean cases (required characteristic IS in the text, or none required):
CL01 (no required chars), CL02 (Российский размер 48-50 and Назначение «мужская» are present), CL04 (adult T-shirt: none required),
FU18 (Вид/Тип шкафа: «металлический для документов»), FU19 (обивка «ткань» given), FU20 (none required),
TO32 (Вид «комбинированные», Длина 160 мм present), TO34 (Тип питания «аккумуляторная» present).

## Failures (top-3 miss or wrong status)

| id | type | query | expected | got top3 | status | domain |
|---|---|---|---|---|---|---|
| CL02 | clean | Куртка зимняя Аляска удлиненная черная мужская размер 48-50 рост 170-176 подкладка полиэстер | 14.13 / ok|ambiguous | 14.13.10.000-00000028 14.11.10.000-00000002 14.13.10.000-00000012 | need_more | clothing |
| FU18 | clean | Шкаф металлический для документов сварной высота 660 мм ширина 420 мм глубина 350 мм масса 19 кг 2 полки | 31.01 / ok|ambiguous | 31.01.11.121-00000001 31.01.11.121-00000005 31.01.11.122-00000001 | need_more | furniture |
| FU19 | clean | Кресло офисное обивка ткань цвет черный высота 1080 мм ширина 650 мм глубина 450 мм | 31.01 / ok|ambiguous | 31.01.12.160-00000005 31.01.12.160-00000006 | need_more | furniture |
| TO32 | clean | Плоскогубцы комбинированные длина 160 мм материал губок инструментальная сталь рукоятка двухкомпонентная | 25.73.3 / ok|ambiguous | 25.73.30.161-00000001 25.73.30.161-00000002 25.73.30.161-00000003 | need_more | tools |
| TO34 | clean | Отвертка аккумуляторная напряжение 3.6 В масса 900 г 1 скорость | 28.24.1 / ok|ambiguous | 28.24.11.000-00000030 28.24.11.000-00000031 28.24.11.000-00000032 | need_more | tools |
