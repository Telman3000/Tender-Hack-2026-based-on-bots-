# Tender Hack 2026 — Автозаполнение ключевых характеристик в СТЕ

Сервис принимает свободное описание товара (название + характеристики в одной строке),
разбирает его, унифицирует характеристики и единицы измерения, поэтапно сужает множество
кодов **КТРУ** до конечного кода и подсвечивает ошибки / нехватку обязательных полей.

Скоуп хакатона: **одежда · мебель · инструменты**.

## Быстрый старт

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux:
# source .venv/bin/activate

pip install -r requirements.txt

# 1) Собрать индекс из материалов организаторов
#    Укажите путь к распакованной папке «Казань 2026» или к zip
python -m scripts.build_index --materials "_materials"

# 2) Запуск API + UI
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Открыть: http://localhost:8000

## Структура

```
app/                 # FastAPI + ядро матчинга
scripts/             # сборка индексов из КТРУ XML / Excel
data/processed/      # SQLite индекс (генерируется локально)
frontend/            # статический UI
docs/                # BPMN, заметки
мысли/               # лог прогонов для тиммейтов
tests/
```

## Ограничения (из ТЗ)

- Без проприетарных LLM API (OpenAI / Gemini / Claude) в готовом решении
- Без платных search API, без low-code/no-code
- Open-source ML допустим, суммарно ≤ 40 ГБ VRAM
- Routers для открытых LLM (Timeweb / Selectel) — ок, предпочтение отечественным

## Репозиторий

https://github.com/Telman3000/Tender-Hack-2026
