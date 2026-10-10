# API `POST /api/analyze`

## Запрос

| Поле | Тип | Описание |
|---|---|---|
| `text` | string, обязательно | Свободное описание товара |
| `characteristics` | `[{name, value, unit}]` \| null | Строки таблицы из UI; перекрывают распознанные из текста с тем же каноническим именем |
| `domain_hint` | `furniture` \| `clothing` \| `tools` \| null | Подсказка домена; другое значение → HTTP 422 |

## Ответ

| Поле | Тип | Описание |
|---|---|---|
| `input_text` | string | Исходный текст |
| `detected_domain` | string \| null | Домен |
| `product_guess` | string \| null | Распознанное наименование (после исправления опечаток) |
| `best_ktru` | object \| null | `{code, name, okpd2, score, required_chars[], matched_chars[]}` |
| `candidates` | `[{code, name, score}]` | До 5 кандидатов, если подходит несколько |
| `status` | string | Старое поле (для совместимости): `not_found` > `error` > `need_more` > `ambiguous` > `ok` |
| `code_status` | `determined` \| `ambiguous` \| `not_found` | Уверенность в коде: `determined` — все оставшиеся кандидаты — вариации одного наименования |
| `card_status` | `complete` \| `incomplete` \| `invalid` | Заполненность карточки: `invalid` — есть ошибки (severity=error), `incomplete` — пусты обязательные характеристики или ничего не распознано |
| `completeness` | object | `{required_total, required_filled, optional_total, optional_filled}` по таблице `characteristics` |
| `characteristics` | array | Таблица характеристик, см. ниже |
| `issues` | array | Проблемы, см. ниже |
| `corrections` | array | Что ядро исправило само, см. ниже |
| `narrowing` | array | Шаги сужения, см. ниже |
| `next_steps` | string[] | Только обязательные шаги (обязательные характеристики и шаги без поля, например «уточните тип товара») |
| `next_steps_detail` | `[{text, field, required}]` | Все шаги; `field` — имя строки таблицы или null |
| `debug` | object | `{raw_count, elapsed_ms}` |

### `characteristics[]`

| Поле | Тип | Описание |
|---|---|---|
| `name` | string | Каноническое имя (КТРУ → портал → новое свойство) |
| `value` | string | Значение (пустая строка — не заполнено) |
| `unit` | string \| null | Единица (для числовых КТРУ — единица КТРУ) |
| `source` | `ktru` \| `portal` \| `new` | Источник имени |
| `user_input` | string \| null | Фрагмент ввода, из которого взято значение |
| `required` | bool | Обязательная характеристика КТРУ |
| `allowed` | string[] \| null | Допустимые значения (только перечисления) |
| `min`, `max` | number \| null | Диапазон числовой характеристики в `unit` |
| `span` | `[start, end]` \| null | Смещения символов в исходном `text`, если значение взято из текста |
| `raw_name`, `canonical_name`, `confidence`, `notes` | — | Служебные/устаревшие |

### `issues[]`

| Поле | Тип | Описание |
|---|---|---|
| `type` | string | `not_allowed`, `out_of_range`, `unit`, `mismatch`, `missing`, `typo`, `ambiguous`, `new_property` |
| `kind` | string | То же, что `type` (совместимость) |
| `field` | string \| null | Характеристика |
| `value`, `expected` | string \| null | Введённое и ожидаемое значение |
| `suggestions` | string[] | До 3 подсказок (`suggestion` — первая, совместимость) |
| `message` | string | Текст для пользователя |
| `severity` | `error` \| `warning` | `new_property` всегда `warning` |
| `span` | `[start, end]` \| null | Смещения в исходном `text` |

### `corrections[]`

| Поле | Тип | Описание |
|---|---|---|
| `field` | string \| null | Характеристика или «Наименование» |
| `kind` | `unit` \| `autofix` \| `typo` \| `translit` | `unit` — перевод/подстановка единицы («27 см» → «270 мм», «750» → «750 мм»); `autofix` — значение исправлено на допустимое КТРУ (нечёткое совпадение ≥ 92, «чорный» → «Черный»); `typo` — исправлено слово в наименовании; `translit` — латиница → кириллица |
| `from`, `to` | string | Было → стало |
| `span` | `[start, end]` \| null | Где в исходном `text` |

### `narrowing[]`

`{step, label, remaining, removed, reason, removed_codes[]}` (+ устаревшие `stage`, `top[]`, `note`).
`label`: «Домен», «Наименование», «ОКПД2», имя характеристики, «Итог». Первый шаг — начальный пул (`remaining` = N).

## Пример (фрагмент)

Запрос `{"text": "Ключ гаечный 17х19 мм длина 27 см цвет чорный"}`:

```json
{
  "status": "need_more", "code_status": "determined", "card_status": "incomplete",
  "completeness": {"required_total": 1, "required_filled": 0, "optional_total": 3, "optional_filled": 2},
  "corrections": [{"field": "Длина разводного ключа", "kind": "unit", "from": "27 см", "to": "270 мм", "span": [28, 33]}],
  "next_steps": ["Укажите: Тип исполнения"],
  "next_steps_detail": [
    {"text": "Укажите: Диэлектрическое покрытие", "field": "Диэлектрическое покрытие", "required": false},
    {"text": "Укажите: Тип исполнения", "field": "Тип исполнения", "required": true}
  ]
}
```
