# BPMN — схема реализации (для защиты)

Ниже — текстовая нотация процесса (перенести в Camunda / draw.io / bpmn.io).

## Процесс: `ClassifyProductToKTRU`

```
[Start] UserSubmitsFreeText
   → Task: FixLayoutAndTypos (раскладка; опечатки — словарь OpenCorpora + словарь КТРУ и портала)
   → Task: DetectDomain (furniture|clothing|tools)
   → Task: ParseFreeText (product + raw characteristics)
   → Task: UnifyCharacteristics
        Gateway: Priority
          1) Match against KTRU char names (эталон)
          2) Else match portal export char names
          3) Else register as NEW property
   → Task: ScoreKtruCandidates (name + domain pool)
   → Task: NarrowByCharacteristics (значения из текста и признаки да/нет)
   → Task: CheckValues (допустимые значения и диапазоны КТРУ, типичные значения в карточках портала)
   → Gateway: UniqueCode?
        YES → Task: CheckRequiredChars
               Gateway: MissingRequired?
                 YES → EndEvent: NeedMoreData (issues + next_steps)
                 NO  → EndEvent: KtruResolved
        NO  → EndEvent: Ambiguous (вопрос по характеристике, которой различаются оставшиеся коды)
```

## Участники

| Lane | Кто | Что делает |
|------|-----|------------|
| User | Менеджер / поставщик | Вводит описание, дополняет по подсказкам |
| System | Сервис autofill | Парсинг, унификация, сужение КТРУ, UI |
| Data | КТРУ + выгрузки ПП | Эталон и практика именования свойств |

## Артефакты на защите

1. Диаграмма BPMN (этот процесс)
2. Живое демо 2–3 кейсов (полный / неполный / с ошибкой)
3. Показ источников характеристик: `ktru` / `portal` / `new`
