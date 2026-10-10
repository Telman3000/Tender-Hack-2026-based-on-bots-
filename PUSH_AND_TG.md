# Git push (только ты) + текст в Telegram

Пуш делает **только владелец**. Агент код не пушит.

## Перед пушем

```powershell
cd "c:\Users\Asus\Desktop\Tender Hack 2026"
$env:PYTHONIOENCODING='utf-8'

# если индекс ещё не собран:
# python -m pip install -r requirements.txt
# python -m scripts.build_index --materials "_materials" --ktru-files 82

python -m pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Проверь http://127.0.0.1:8000 — примеры без «Идеал».

`catalog.db`, `_materials/`, xlsx/xml/zip в git **не** кладём.

## Push в GitHub

Репо: https://github.com/Telman3000/Tender-Hack-2026

```powershell
cd "c:\Users\Asus\Desktop\Tender Hack 2026"

git init
git remote add origin https://github.com/Telman3000/Tender-Hack-2026.git
# если remote уже есть:
# git remote -v

git checkout -b main
git add .
git status
# НЕ должно быть: _materials/, data/processed/catalog.db, *.xlsx, transcripts/

git commit -m "feat: MVP STE autofill with KTRU matching (baseline)"

git pull origin main --allow-unrelated-histories
# конфликт LICENSE — оставь их/оба

git push -u origin main
```

Логин: `gh auth login` или Personal Access Token.

## Текст в Telegram

```
Tender Hack 2026 — baseline MVP в репо

https://github.com/Telman3000/Tender-Hack-2026

Что есть:
• текст → характеристики → унификация (КТРУ → портал → new) → сужение КТРУ
• UI :8000, API /api/analyze
• BPMN черновик: docs/process.bpmn
• мысли/ — лог решений (читай перед тем как чинить то же)

Поднять:
pip install -r requirements.txt
# Казань 2026.zip → _materials/
python -m scripts.build_index --materials "_materials" --ktru-files 82
uvicorn app.main:app --reload --port 8000

Важно: статусы «Неоднозначно / Нужны уточнения» — норма для MVP и КТРУ (группа вариаций), не баг.
Фичи вне ТЗ не пилим. Без OpenAI/Gemini/Claude в готовом решении.

Дальше: опечатки, unit-sanity, BPMN, UI-kit. Находки → мысли/00N_....md
```
