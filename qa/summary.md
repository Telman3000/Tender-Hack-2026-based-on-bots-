# QA eval — feature/qa@a578278, 2026-10-10 10:20

Cases: 45; domain_hint=on. Status accepted sets per case are in cases.csv (clean: ok, or ambiguous only if the expected group is in top-3; incomplete: need_more|ambiguous; error: anything except ok).

| slice | n | top-1 | top-3 | group | status | false-confident (err) | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|---|---|---|---|
| ALL | 45 | 7% | 9% | 9% | 67% | 7% | 326 | 445 | 798 |
| category=clothing | 15 | 13% | 20% | 20% | 73% | 0% | 176 | 283 | 329 |
| category=furniture | 15 | 7% | 7% | 7% | 60% | 20% | 346 | 392 | 518 |
| category=tools | 15 | 0% | 0% | 0% | 67% | 0% | 359 | 445 | 798 |
| type=clean | 15 | 7% | 7% | 7% | 7% | - | 359 | 518 | 798 |
| type=error | 15 | 7% | 7% | 7% | 93% | 7% | 331 | 392 | 407 |
| type=incomplete | 15 | 7% | 13% | 13% | 100% | - | 304 | 346 | 377 |

## Failures (top-3 miss or wrong status)

| id | type | query | expected | got top3 | status | domain |
|---|---|---|---|---|---|---|
| CL01 | clean | Костюм рабочий мужской л08-КБР размер 48-50 рост 170-176 ткань смесовая | 14.12 / ok|ambiguous |  | ambiguous | clothing |
| CL03 | clean | Халат женский для уборщиц у01-ХЛ рукав длинный размер 48-50 рост 158-164 | 14.12.2 / ok|ambiguous |  | ambiguous | clothing |
| CL04 | clean | Футболка хлопок 100% красная размер 48-50 масса 179 г | 14.14.3 / ok|ambiguous | 14.12.10.000-00000001 14.12.10.000-00000002 32.50.50.000-00000260 | ambiguous | clothing |
| CL05 | clean | Ботинки рабочие утепленные верх натуральная кожа подошва полиуретан литьевой метод крепления размер 47 | 15.20.3 / ok|ambiguous | 15.11.50.000-00000003 15.11.50.000-00000002 15.11.50.000-00000001 | ambiguous | clothing |
| CL06 | incomplete | Костюм рабочий | 14.12 / need_more|ambiguous |  | need_more | clothing |
| CL07 | incomplete | Куртка | 14.1 / need_more|ambiguous |  | need_more | clothing |
| CL08 | incomplete | Халат размер 48 | 14.12 / need_more|ambiguous |  | ambiguous | clothing |
| CL09 | incomplete | Ботинки | 15.20 / need_more|ambiguous |  | need_more | clothing |
| CL11 | error | Костюм рабочий размер 148-150 рост 1700-1760 см | 14.12 / need_more|ambiguous|error |  | ambiguous | clothing |
| CL13 | error | Кастюм рабочий мужкой размер 48-50 | 14.12 / need_more|ambiguous|error |  | ambiguous | clothing |
| CL14 | error | Kurtka zimnyaya muzhskaya razmer 50 | 14.12 / need_more|ambiguous|error |  | need_more | clothing |
| CL15 | error | Футболка хлопок 300% размер 48-50 | 14.14.3 / need_more|ambiguous|error | 14.12.10.000-00000001 14.12.10.000-00000002 | ambiguous | clothing |
| FU16 | clean | Стол офисный угловой письменный столешница ЛДСП толщина 16 мм размер 1200х750х1200 мм кромка ПВХ | 31.01 / ok|ambiguous |  | ambiguous | furniture |
| FU17 | clean | Стул офисный обивка ткань цвет черный высота 820 мм глубина 530 мм масса 4 кг | 31.01 / ok|ambiguous |  | ambiguous | furniture |
| FU18 | clean | Шкаф металлический для документов сварной высота 660 мм ширина 420 мм глубина 350 мм масса 19 кг 2 полки | 31.01 / ok|ambiguous |  | ambiguous | furniture |
| FU19 | clean | Кресло офисное обивка ткань цвет черный высота 1080 мм ширина 650 мм глубина 450 мм | 31.01 / ok|ambiguous |  | ambiguous | furniture |
| FU20 | clean | Стеллаж металлический высота 2000 мм ширина 1000 мм глубина 300 мм 6 полок нагрузка на полку 100 кг | 31.01 / ok|ambiguous |  | ambiguous | furniture |
| FU22 | incomplete | Стул офисный | 31.01 / need_more|ambiguous |  | need_more | furniture |
| FU23 | incomplete | Шкаф для документов | 31.01 / need_more|ambiguous |  | need_more | furniture |
| FU24 | incomplete | Кресло черное | 31.0 / need_more|ambiguous |  | need_more | furniture |
| FU25 | incomplete | Стеллаж 6 полок | 31.01 / need_more|ambiguous | 31.09.10.000-00000001 31.02.10.000-00000001 | need_more | furniture |
| FU26 | error | Стол офисный высота 75000 мм ширина 1200 мм | 31.01 / need_more|ambiguous|error | 32.50.30.110-00000001 | ok | furniture |
| FU27 | error | Стул офисный высота 820 кг цвет черный | 31.01 / need_more|ambiguous|error |  | ambiguous | furniture |
| FU28 | error | Стол офисный ЛДСП цвет фиолетово-прозрачный материал плазма | 31.01 / need_more|ambiguous|error | 43.32.10.000-00000002 43.32.10.000-00000001 | ambiguous | furniture |
| FU29 | error | Шкав металический для дакументов | 31.01 / need_more|ambiguous|error |  | need_more | furniture |
| FU30 | error | Stol ofisnyj LDSP 1200x750 mm | 31.01 / need_more|ambiguous|error |  | need_more | furniture |
| TO31 | clean | Ключ гаечный кольцевой двухсторонний 17х19 мм сталь 40Х длина 270 мм покрытие цинковое | 25.73.3 / ok|ambiguous |  | ambiguous | tools |
| TO32 | clean | Плоскогубцы комбинированные длина 160 мм материал губок инструментальная сталь рукоятка двухкомпонентная | 25.73.3 / ok|ambiguous |  | ambiguous | tools |
| TO33 | clean | Дрель ударная мощность 650 Вт диаметр сверления дерево 30 мм масса 3.2 кг | 28.24.1 / ok|ambiguous |  | ambiguous | tools |
| TO34 | clean | Отвертка аккумуляторная напряжение 3.6 В масса 900 г 1 скорость | 28.24.1 / ok|ambiguous |  | ambiguous | tools |
| TO35 | clean | Молоток отбойный мощность 1510 Вт масса 15.7 кг | 28.24.1 / ok|ambiguous |  | ambiguous | tools |
| TO36 | incomplete | Молоток | 25.73|28.24 / need_more|ambiguous |  | need_more | tools |
| TO37 | incomplete | Ключ | 25.73.3 / need_more|ambiguous |  | need_more | tools |
| TO38 | incomplete | Дрель | 28.24.1 / need_more|ambiguous |  | need_more | tools |
| TO39 | incomplete | Пила | 25.73.2|28.24.1 / need_more|ambiguous |  | need_more | tools |
| TO40 | incomplete | Отвертка | 25.73.3|28.24.1 / need_more|ambiguous |  | need_more | tools |
| TO41 | error | Дрель ударная мощность 650 кг масса 3 Вт | 28.24.1 / need_more|ambiguous|error |  | ambiguous | tools |
| TO42 | error | Ключ гаечный 170х190 мм длина 27 м | 25.73.3 / need_more|ambiguous|error |  | ambiguous | tools |
| TO43 | error | Плоскагубцы камбинированые 160мм | 25.73.3 / need_more|ambiguous|error |  | need_more | tools |
| TO44 | error | Drel udarnaya 650 Vt | 28.24.1 / need_more|ambiguous|error |  | need_more | tools |
| TO45 | error | Молоток отбойный напряжение 2200000 В | 28.24.1 / need_more|ambiguous|error |  | need_more | tools |
