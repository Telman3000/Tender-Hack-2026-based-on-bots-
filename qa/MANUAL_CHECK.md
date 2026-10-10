# Как проверить руками (Windows, PowerShell)

```powershell
cd C:\Users\Asus\Desktop\Vtoroy_work
git clone https://github.com/Telman3000/Tender-Hack-2026-based-on-bots-.git check
cd check
git checkout origin/feature/core        # или нужный коммит, например d35047b
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts\build_index.py --materials C:\Users\Asus\Desktop\Vtoroy_work\Kazan2026_unzipped   # ~1–2 мин, 3391 позиций КТРУ
.venv\Scripts\python -m pytest -q                                       # все тесты должны пройти
```

Проверки QA (файлы из ветки feature/qa):
```powershell
git checkout origin/feature/qa -- qa
.venv\Scripts\python qa\run_eval.py                       # 45 кейсов -> qa\summary.md
.venv\Scripts\python qa\run_eval.py --cases=holdout.csv   # холдаут 45
.venv\Scripts\python qa\run_holdout.py                    # ошибки 30 + ложные тревоги
git checkout -- qa                                        # вернуть файлы как были
```

Сервер: `.venv\Scripts\python -m uvicorn app.main:app --port 8809`, открыть http://127.0.0.1:8809 . Остановить: Ctrl+C.

Три сценария в UI:
1. «Ключ гаечный 17х19 мм длина 27 см цвет чорный» -> код 25.73.30.171, исправления 27 см -> 270 мм и «чорный», просит «Тип исполнения».
2. «Стол офисный ЛДСП высота 750 мм ширина 1200 мм» -> в таблице поменять высоту 750 на 900: результат и текст пересчитываются;
   кнопка «Сбросить правки таблицы» возвращает 750 в таблице, тексте и результате.
3. «Кресло офисное вид материала обивки спинки бетон» -> ошибка «такого значения нет в КТРУ» с подсказками допустимых материалов.
"""

## Порядок слияния
1. feature/core d35047b -> main (fast-forward, конфликтов нет). Перед этим желательно исправить 3 ложные ошибки (H04, H17, H27) и серый пункт «Исправьте …».
2. feature/ui db881e8 -> main после ядра (конфликтов нет; UI работает и со старым контрактом через fallback).
3. Обновить цифры в presentation*.pptx (см. qa/summary.md) и только потом — feature/qa (отчёты).

## Проверка за 5 минут (после сборки индекса)
1. `.venv\Scripts\python -m uvicorn app.main:app --port 8809`, открыть http://127.0.0.1:8809 , F12 -> Console без красных ошибок.
2. «Ключ гаечный 170х190 мм длина 27 м» (инструменты): красная подсветка «27 м», «Было → стало: 27 м → 27000 мм», бейджи «Код: определён», «Карточка: есть ошибки».
3. Исправить в тексте на «270 мм»: ошибка ушла; заполнить «Тип исполнения» = B -> «Карточка: заполнена».
4. «Ключ» -> «не хватает обязательных: 1», необязательные пункты серые.
5. «Стол офисный ЛДСП высота 750 мм ширина 1200 мм цвет серый»: в таблице 750 -> 900 (текст тоже меняется), «Сбросить правки таблицы» -> снова 750.
6. «Кресло офисное вид материала обивки спинки бетон» -> ошибка «такого значения нет в КТРУ» и подсветка «бетон».
7. `.venv\Scripts\python -m pytest -q` -> 58 passed.
