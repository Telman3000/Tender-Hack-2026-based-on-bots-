# Red-team breaks (KTRU matching / `POST /api/analyze`)

**Branch:** `cursor/red-team-ktru-breaks-3b39`  
**Environment:** `data/processed/catalog.db` built **2026-10-11** from official hackathon materials under `_materials/yandex_retry2/` (see Setup). Server: `uvicorn app.main:app` on `127.0.0.1:8000`.

## Setup (repro)

1. **Materials (official, Yandex Disk):** `yadown` succeeded 2026-10-11 → tree copied to `_materials/yandex_retry2/` (includes `КТРУ/КТРУ xml.zip` ~102 MB and full `Примеры выгрузок/{Одежда,Мебель,Инструменты}.xlsx`). Earlier mirror-only builds used `scripts/assemble_materials_from_mirror.py` + `scripts/create_minimal_portal_fixture.py` (see BR-045–BR-048 notes).
2. `python -m scripts.build_index --materials _materials/yandex_retry2` → **3030** KTRU, **60000** `portal_ste`, **99498** `portal_chars` (typical hackathon scale).
3. `uvicorn app.main:app --host 127.0.0.1 --port 8000` (reads `data/processed/catalog.db` via `CATALOG_DB` default).

**Index sanity:** for QA CL01 code `14.12.10.000-00000002`, table `ktru_char_values` has **0** rows (only 2-byte `chars_json` stub) — drives BR-052/BR-048 on full export.

---

## Break catalog

| id | severity | category | hypothesis (short) |
|----|----------|----------|-------------------|
| [BR-001](#br-001) | critical | wrong_ktru | `domain_hint` forces wrong domain pool → industrial KTRU for office furniture |
| [BR-002](#br-002) | high | out_of_scope | Cross-domain hint yields silent `not_found` without `out_of_scope` |
| [BR-003](#br-003) | critical | wrong_ktru | Unquoted CSV comma splits semantics; wrong desk vs conference table |
| [BR-004](#br-004) | high | card_status | `status=ok`, `card_status=complete` despite `new_property` on «Рост» |
| [BR-005](#br-005) | high | new_property | «Содержание хлопок» invented as NEW with `status=ok` instead of material KTRU field |
| [BR-006](#br-006) | high | wrong_ktru | Holdout H09: rubber moulded boots → metal-toe shoe code |
| [BR-007](#br-007) | high | wrong_ktru | QA CL08: «Халат размер 48» → medical халат (14.14) vs spec clothing (14.12) |
| [BR-008](#br-008) | medium | demo_misleading | README demo «10.8 Вт» accepted as KTRU «Мощность» without unit sanity |
| [BR-009](#br-009) | medium | typo | «резиновый» → «бензиновый» typo suggestion |
| [BR-010](#br-010) | medium | typo | «резиновая» → «резина» corrupts product wording |
| [BR-011](#br-011) | medium | validation | Absurd unit fix suggestion `99999 см` for `99999 мм` |
| [BR-012](#br-012) | medium | source_order | `source: "portal"` on characteristics with **empty** portal index |
| [BR-013](#br-013) | medium | performance | Single analyze >100 ms on huge repetitive text |
| [BR-014](#br-014) | low | typo | «на колесах» → «колесная» false typo on valid phrase |
| [BR-015](#br-015) | medium | fill | `fill: null` for positions that still expose KTRU characteristics (e.g. electric tool group) |
| [BR-016](#br-016) | medium | unit_guess | «высота 1.10» parsed as **1.10 m** not mm/cm disambiguation for furniture |
| [BR-017](#br-017) | medium | typo | QA E26 «Шкав» not corrected; product name keeps typo |
| [BR-018](#br-018) | high | card_status | QA CL01 (clean): `ok`+`complete` with «Рост» as `new` |
| [BR-019](#br-019) | medium | performance | 50 concurrent analyzes: p50 ≈232 ms (>>100 ms single-request budget) |
| [BR-020](#extended) | critical | wrong_ktru | User «18 В» on hammer → electric tool KTRU, `ok`+`complete` |
| [BR-021](#extended) | high | wrong_ktru | «об/мин» on screwdriver → шуруповерт 28.24 |
| [BR-022](#extended) | high | wrong_ktru | «Лобзик ручной» → фрезer 28.24 |
| [BR-023](#extended) | critical | wrong_ktru | Wardrobe + `domain_hint: tools` → window hardware 25.72 |
| [BR-024](#extended) | medium | new_property | Pipe-separated text → junk `new` char «Стол»=«письменный» |
| [BR-025](#extended) | high | wrong_ktru | Violin + tools hint → pencil sharpener 25.71 |
| [BR-026](#extended) | high | wrong_ktru | Bit set text → kitchen knife set 25.71 |
| [BR-027](#extended) | high | card_status | Suit size 44 → `ok`+`complete` (footwear-sized) |
| [BR-028](#extended) | high | new_property | UI «Рост» still `new` with `complete` |
| [BR-029](#extended) | high | wrong_ktru | «Отвертка» + Тип аккумуляторная → hand-tool KTRU, `ok` |
| [BR-030](#extended) | high | wrong_ktru | Semicolons in text → «Стол администратора» not письменный |
| [BR-031](#extended) | medium | wrong_ktru | «17х19» → разводной wrench not fixed key |
| [BR-032](#extended) | medium | out_of_scope | Drill + `domain_hint: clothing` → `not_found`, `card_status: complete` |

---

### BR-001

- **severity:** critical  
- **category:** wrong_ktru / domain_hint abuse  

**Input (JSON):**

```json
{"text": "Стол письменный ЛДСП высота 750 мм", "domain_hint": "tools"}
```

**Expected:** Reject hint vs product mismatch, or keep furniture domain and return `31.01.10.*` writing desk / `out_of_scope` — not machine-tool furniture.

**Actual:** `detected_domain: "tools"`, `best_ktru.code: "28.41.40.000-00000008"`, `best_ktru.name: "Стол металлический под станок"`, `status: "ambiguous"`, `out_of_scope: false`.

**Hypothesis:** `domain_hint` overrides detection and searches tools KTRU only; fuzzy name match on «стол» picks unrelated 28.x machine table.

---

### BR-002

- **severity:** high  
- **category:** out_of_scope / UX  

**Input:**

```json
{"text": "Костюм рабочий", "domain_hint": "furniture"}
```

**Expected:** `out_of_scope: true` with explanation, or auto-switch to clothing domain.

**Actual:** `status: "not_found"`, `best_ktru: null`, `out_of_scope: false`, no `message` — looks like “we failed to match” rather than “wrong category”.

---

### BR-003

- **severity:** critical  
- **category:** wrong_ktru / csv  

**Input:** CSV upload (UTF-8, header `name`, delimiter `none` per API rules):

```csv
name
Стол, письменный
```

**Expected:** Same code family as `Стол письменный` → `31.01.10.*` «Стол письменный».

**Actual:** Parsed name `Стол, письменный` → `product_guess: "Стол"`, `best_ktru.code: "31.01.12.110-00000003"`, `best_ktru.name: "Стол для переговоров"`.

**Hypothesis:** Comma inside unquoted “single column” CSV is intentional per API docs, but comma breaks tokenization / product guess.

---

### BR-004

- **severity:** high  
- **category:** card_status / new_property  

**Input:**

```json
{"text": "Костюм рабочий мужской размер 48-50 рост 170-176", "domain_hint": "clothing"}
```

**Expected:** `need_more` or map «рост» to existing KTRU size fields; `card_status` at most `incomplete`; no `ok` while inventing properties.

**Actual:** `status: "ok"`, `code_status: "determined"`, `card_status: "complete"`, issue `new_property` on «Рост», characteristic `{name: "Рост", source: "new", value: "170"}`, `missing_characteristics: []`, `fill: null`.

---

### BR-005

- **severity:** high  
- **category:** new_property  

**Input:**

```json
{"text": "Футболка хлопок 100% красная размер 48-50", "domain_hint": "clothing"}
```

**Expected:** Material composition mapped to KTRU textile / fibre fields, not a new «Содержание хлопок».

**Actual:** `status: "ok"`, `{name: "Содержание хлопок", source: "new", value: "100"}`, `new_property` warning only.

---

### BR-006

- **severity:** high  
- **category:** wrong_ktru  

**Input:**

```json
{"text": "Сапоги резиновые с защитным подноском (размер 44) Вид крепления подошвы литьевой Вид средства защиты ног Сапоги Вид товаров Одежда", "domain_hint": "clothing"}
```

**Expected (holdout H09):** prefix `15.20.11.113` (rubber moulded boots).

**Actual:** `best_ktru.code: "15.20.31.000-00000003"`, `best_ktru.name: "Обувь с защитным металлическим подноском"`, `status: "need_more"`.

---

### BR-007

- **severity:** high  
- **category:** wrong_ktru  

**Input:**

```json
{"text": "Халат размер 48", "domain_hint": "clothing"}
```

**Expected (QA CL08):** group `14.12.*` workwear халат.

**Actual:** `best_ktru.code: "14.14.10.000-00000003"`, `best_ktru.name: "Халат"`, `status: "need_more"` (medical/other 14.14 line).

---

### BR-008

- **severity:** medium  
- **category:** unit / demo  

**Input (README demo):**

```json
{"text": "Дрель-шуруповерт аккумуляторная мощность 10.8 Вт цвет серый", "domain_hint": "tools"}
```

**Expected:** Flag unlikely 10.8 W or treat as voltage typo (common marketing copy); or `error`/`warning` on power.

**Actual:** `Мощность: "10.8"` accepted on KTRU, no error issues, `status: "need_more"`.

---

### BR-009

- **severity:** medium  
- **category:** typo  

**Input:**

```json
{"text": "Шпатель STAYER резиновый 150 мм", "domain_hint": "tools"}
```

**Expected:** No typo suggestion, or neutral spelling fix.

**Actual:** Issue `typo`: «резиновый» → «**бензиновый**».

---

### BR-010

- **severity:** medium  
- **category:** typo  

**Input:**

```json
{"text": "Киянка резиновая TOPEX 680 гр", "domain_hint": "tools"}
```

**Expected:** Keep adjective «резиновая».

**Actual:** Issue `typo`: «резиновая» → «резина».

---

### BR-011

- **severity:** medium  
- **category:** validation  

**Input:**

```json
{
  "text": "Стол письменный",
  "domain_hint": "furniture",
  "characteristics": [{"name": "Высота", "value": "99999", "unit": "мм"}]
}
```

**Expected:** Error on unrealistic height; suggestions in mm or human ranges.

**Actual:** Error message OK, but `suggestions: ["99999 см"]` — same numeric magnitude, wrong unit (still ~999 m).

---

### BR-012

- **severity:** medium  
- **category:** source_order / data  

**Input:**

```json
{"text": "Стол офисный ДСП высота 750 мм ширина 1200 мм глубина 600 мм цвет серый", "domain_hint": "furniture"}
```

**Expected:** With portal index loaded, `source: "portal"` only for portal-backed fields; otherwise KTRU.

**Actual (with `portal_ste=0`):** Characteristics `{name: "Высота", source: "portal", ...}` (and similar) despite empty portal tables in `catalog.db`.

---

### BR-013

- **severity:** medium  
- **category:** performance  

**Input:**

```json
{"text": "Стол " + "письменный " repeated 5000 times, "domain_hint": "furniture"}
```

(Copy-pasteable generator in `qa/breaks_cases.json`.)

**Expected:** Per red-team budget: single request ≤100 ms (product requirement in task brief).

**Actual:** ~180–190 ms (`debug.elapsed_ms` similar), HTTP 200.

---

### BR-014

- **severity:** low  
- **category:** typo  

**Input:**

```json
{"text": "Стул офисный на колесах металл черный", "domain_hint": "furniture"}
```

**Expected:** No typo on «на колесах».

**Actual:** `typo` issue: «колесах» → «колесная».

---

### BR-015

- **severity:** medium  
- **category:** fill / API contract  

**Input:**

```json
{"text": "Молоток аккумуляторный ударный 18 В", "domain_hint": "tools"}
```

**Expected:** `fill` counter describing KTRU characteristics for chosen code.

**Actual:** `best_ktru` set (`28.24.10.000-00000001`), long `characteristics` list, but `fill: null` (same for «Отвертка крестовая PH2»).

---

### BR-016

- **severity:** medium  
- **category:** unit_guess  

**Input:**

```json
{"text": "стол офсный дсп высота 1.10 цвет красный", "domain_hint": "furniture"}
```

**Expected:** Prefer mm for furniture dimensions (`1100 мм`) or ask clarification.

**Actual:** `{name: "Высота", value: "1.10", unit: "м"}` — treats bare decimal as meters.

---

### BR-017

- **severity:** medium  
- **category:** typo  

**Input:**

```json
{"text": "Шкав для одежды металлический", "domain_hint": "furniture"}
```

**Expected (QA E26):** `typo` issue suggesting «Шкаф»; normalized product name.

**Actual:** `product_guess` unchanged «Шкав…», no `typo` issue; only `missing` warnings; `best_ktru.code: 31.01.11.121-00000001`.

---

### BR-018

- **severity:** high  
- **category:** card_status / new_property  

**Input:**

```json
{"text": "Костюм рабочий мужской л08-КБР размер 48-50 рост 170-176 ткань смесовая", "domain_hint": "clothing"}
```

**Expected (QA CL01 clean):** Map «рост» to clothing size KTRU fields; `card_status` not `complete` while `new_property` present.

**Actual:** Same as BR-004 pattern: `status: ok`, `card_status: complete`, «Рост» `source: new`.

---

### BR-019

- **severity:** medium  
- **category:** performance  

**Input:** `python scripts/load_test.py --url http://127.0.0.1:8000 --n 100 --concurrency 50`

**Expected:** Single-request SLA ≤100 ms (task brief); stable under moderate concurrency.

**Actual:** 100/100 HTTP 200, but **p50 ≈ 232 ms**, p95 ≈ 306 ms, max ≈ 353 ms (warm single requests ~7–20 ms).

**Hypothesis:** Shared `CatalogEngine` + thread pool contention / SQLite read locking under parallel `/api/analyze`.

---

### Extended catalog (verified BR-020–BR-032) {#extended}

Full JSON bodies: `qa/breaks_cases.json`. Summary:

| id | Input (abbrev.) | Expected | Actual (code / status) |
|----|-----------------|----------|-------------------------|
| BR-020 | Молоток + char Напряжение 18 В | 25.73 hammer | **28.24.10.000-00000001**, `ok`/`complete` |
| BR-021 | Отвертка + 3000 об/мин | 25.73 hand | **28.24.11.000-00000030** Шуруповерт |
| BR-022 | Лобзик ручной | 28.24 jigsaw | **28.24.11.000-00000010** Фрезer |
| BR-023 | Шкаф… + hint tools | 31.01 wardrobe | **25.72.14.120-00000001** window hardware |
| BR-024 | Стол письменный \| Высота… | no junk new rows | `new` «Стол»=«письменный» |
| BR-025 | Скрипка + hint tools | out_of_scope | **25.71.13** pencil sharpener |
| BR-026 | Набор бит… отвертка | bit/driver | **25.71.11** knife set |
| BR-027 | Костюм рабочий размер 44 | incomplete / size sanity | `ok`/`complete` 14.12.10.* |
| BR-028 | UI characteristics Рост 170-176 | KTRU height | `new` Рост, `ok`/`complete` |
| BR-029 | Отвертка + Тип аккумуляторная | power tool or reject | 25.73 hand tool, `ok` |
| BR-030 | Стол; письменный; ЛДСП… | 31.01.10 desk | **31.09.10** admin desk |
| BR-031 | Ключ гаечный 17х19 | fixed 17×19 | **25.73.30.171** разводной |
| BR-032 | Дрель 800 Вт + hint clothing | out_of_scope | `not_found`, **`card_status: complete`** |

---

## Count by severity

| severity | count |
|----------|------:|
| critical | 5 |
| high | 41 |
| medium | 37 |
| low | 3 |
| **total** | **86** |

### Round 2 (BR-033–BR-044) {#round2}

Yandex Disk portal XLSX: **still HTTP 500** (retried yadown + API ×3). Index unchanged (`portal_ste=0`).

| id | severity | category | summary |
|----|----------|----------|---------|
| BR-033 | high | duplicate_chars | Duplicate UI «Масса молотка» 500 g + 900 g → **two KTRU rows** (0.5 & 0.9 kg), `status=ok` |
| BR-034 | medium | out_of_scope | «Каталка медицинская…» → `not_found`, **`out_of_scope: false`** |
| BR-035 | high | numeric_parse | `7.5e2 мм` → parses **`7`**, not 750 |
| BR-036 | high | numeric_parse | `1\u2009200 мм` (thin space) → **1 mm**, not 1200 |
| BR-037 | medium | csv_encoding | cp1251 `наименование;…` header → **422** «нет строк» (encoding/header) |
| BR-038 | high | csv_quotes | Quoted `"Стол, письменный, ЛДСП"` → **31.09 admin desk**, guess «Стол» |
| BR-039 | medium | unit | «47 дюймов» → **47 mm**, no inch conversion |
| BR-040 | high | fake_code | Text «код КТРУ 31.01.10.000-00000006…» → **`not_found`** (worse than ignore) |
| BR-041 | medium | unicode | Fullwidth `１２００` stored verbatim in «Ширина» |
| BR-042 | medium | characteristics | Text 750 mm + UI 500 mm → **500 wins**, no conflict issue |
| BR-043 | medium | injection | 500-char characteristic **name** → `new_property` |
| BR-044 | low | validation | Emoji in «Цвет» value accepted (`🔥красный`) |

**Examples (copy-paste JSON):**

```json
{"text": "Молоток слесарный", "domain_hint": "tools", "characteristics": [{"name": "Масса молотка", "value": "500", "unit": "г"}, {"name": "Масса молотка", "value": "900", "unit": "г"}]}
```

```json
{"text": "Стол письменный высота 7.5e2 мм", "domain_hint": "furniture"}
```

```json
{"text": "Стол письменный ширина 1\u2009200 мм", "domain_hint": "furniture"}
```

cp1251 CSV (raw bytes): `наименование;Стол письменный\n` encoded cp1251 → POST `/api/analyze/csv`.

### Round 2b — with minimal portal fixture {#round2b}

After rebuilding `catalog.db` with minimal `Одежда.xlsx` / `Мебель.xlsx` / `Инструменты.xlsx`:

| id | severity | category | summary |
|----|----------|----------|---------|
| BR-045 | medium | batch | Batch `{id:1}` twice → **same id**, different KTRU (стол vs молоток) |
| BR-046 | medium | mixed_language | `T-shirt cotton 100% size L` + `clothing` → `not_found`, **`out_of_scope: false`** |
| BR-047 | low | portal_naming | CL01: portal field **`«рost»` lowercase**, not KTRU-style «Рост» |
| BR-048 | high | card_status | CL01: `card_status=complete`, `completeness.required_total=0` while KTRU `14.12.10.*` has **empty `required_json` in index** |

**Note:** BR-004/BR-005 **do not reproduce** «Рост»/«Содержание хлопок» as `new` with minimal portal (mapped to `portal`). They remain valid for **KTRU-only** index / missing exports.

**BR-033** (duplicate «Масса молотка») **still reproduces** with portal loaded.

| id | severity | category | summary |
|----|----------|----------|---------|
| BR-049 | medium | outdated_code | Identical «Стол письменный» variants: top-1 **`31.01.10.000-00000004` (v10)** while **`…00000006` (v12)** also in candidates |
| BR-050 | high | csv | CSV `name\nname\nСтол` → row **`name`** analyzed as product (translit «наме», `out_of_scope`) instead of skipping repeated header |

```json
{"text": "Стол письменный ЛДСП", "domain_hint": "furniture"}
```
(check `best_ktru.code` vs candidates versions in response)

CSV bytes UTF-8:
```
name
name
Стол
```

### BR-051

- **severity:** medium  
- **category:** performance  

**Input:** `{"text": "Стол " + "x" * 20000, "domain_hint": "furniture"}`

**Expected:** Single analyze ≤100 ms (task brief).

**Actual:** `debug.elapsed_ms` ≈ **248 ms** (HTTP 200).

---

### Round 3 — official portal index (`yandex_retry2`) {#round3}

Full portal rebuild (`60000` STE). Copy-paste bodies: `qa/breaks_cases.json` + runner `qa/redteam_round3.py`.

| id | severity | category | summary |
|----|----------|----------|---------|
| BR-052 | critical | card_status / portal | QA **CL01**: `status=ok`, `card_status=complete`, **`characteristics` = 2× `source: portal` only** («Размер», «Размер/рост»); **`ktru_char_values` = 0** in DB for `14.12.10.000-00000002`; `fill=null`, `missing_characteristics=[]` |
| BR-053 | high | homoglyph | `St\u043el pismennyi…` (Latin + Cyrillic «о») → **`not_found`**, no desk candidate (translit path fails) |
| BR-054 | high | mixed_language | `Стол pismennyi ЛДСП` → **`31.09.10.000-00000003`**, not `31.01.10` writing desk |
| BR-055 | high | wrong_ktru | `Гитара акустическая` + `domain_hint: tools` → **`28.25.14.129-00000013`** «Установка термокаталитическая» |
| BR-056 | medium | out_of_scope | `Пианино акустическое` + `furniture` → `not_found`, **`out_of_scope: false`** |
| BR-057 | high | unit_guess | «Молоток… **масса 0.5 т**» → stored **`0.5` кг** (`unit` warning only), not 500 kg; contrasts with **500 kg → error** (realistic cap) |
| BR-058 | medium | csv | Tab CSV `name\ttext` + `\tСтол письменный` → row **`Пустое наименование`** (product in wrong column) |
| BR-059 | high | mixed_language | `Kostium rabochii razmer 48-50` + `clothing` → **`14.12.30.160-00000515`** «Очки… от радиации», `ambiguous` |
| BR-060 | medium | numeric_parse | «ширина **120-130**» → **single value `120` мм**, upper bound dropped |
| BR-061 | high | validation | Holdout **H17** (диван + «высокоэластичный поролон»): `not_allowed` issue severity **`warning` only**, card stays **`incomplete`** not `invalid` |
| BR-062 | high | csv | **Double UTF-8 BOM** + `name\nСтол` → **`31.01.12.110`** conference table (BOM corrupts header/name) |
| BR-063 | medium | performance | `POST /api/analyze/batch?stream=1` × **500** identical rows → **~13.3 s** wall (>>10 s CSV/batch budget) |
| BR-064 | high | wrong_ktru | «**Труба медная** 15 мм» + `tools` → **`28.25.14.125-00000002` Труба Вентури** |
| BR-065 | high | wrong_ktru | «**Барабан малый** латунный» + `tools` → **`28.21.12.000-00000004` Барабан прокалочный** (not percussion) |
| BR-066 | medium | numeric_parse | CL01 text «48-**50**» / «170-**176**» → portal values **`48`** and **`170` only** (range tail lost) |
| BR-067 | high | wrong_ktru | «**Шина автомобильная** 205/55 R16» + `tools` → **`28.41.30.000-00000011` Машина газопальная** |
| BR-068 | high | wrong_ktru | «**Футболка** хлопок **100％**» (fullwidth percent) → **`14.14.30.110`** without mapped composition |
| BR-069 | medium | card_status | «Костюм рабочий… **размер 50**» → `ok`/`complete` with **one** portal field (no «Размер/рост») |
| BR-070 | medium | wrong_ktru | SQL-ish `Стол'; DROP TABLE…` → **`31.01.12.110`** conference table, `ambiguous` |
| BR-071 | high | wrong_ktru | «**Кресло-коляска** инвалидное» → **`31.01.12.160` Кресло офисное** |
| BR-072 | high | wrong_ktru | «**Верёвка** полипропиленовая…» + `tools` → **`28.21.11.111` Горелка промышленная** |
| BR-073 | medium | out_of_scope | Med/PP E / food-style lines (`Парацетамол`, `Консервы`, `Лампа LED`, `Бетон`…) → `not_found`, **`out_of_scope: false`** |
| BR-074 | high | duplicate_chars | **40× UI** `Поле0…Поле39` = `x` → **40 portal rows** canonical **`«Пол»`=`x`** (prefix collision on portal canon) |
| BR-075 | high | wrong_ktru | Portal-style «**Подставка для ноги гитариста**» → **`31.01.11.150-00000017`** (generic furniture, not music accessory) |
| BR-076 | medium | outdated_code | Text cites **`…00000006` and `…00000004`** → still picks **`31.01.10.000-00000004`** |
| BR-077 | medium | performance | `POST /api/analyze/csv?stream=1` **500** rows → **~15.3 s** wall (same class as BR-063) |
| BR-078 | medium | mixed_language | **`Office desk laminate 1200mm`** + `furniture` → `not_found`, **`out_of_scope: false`** |
| BR-079 | high | out_of_scope | **`办公桌 1200毫米`** → `not_found`, **`out_of_scope: true`** while English desk (BR-078) is false — **inconsistent language UX** |
| BR-080 | high | wrong_ktru | «**Ботинки рабочие костюм комплект**» → **`15.20.32.126-00000001`** vibro **shoe**, not suit/boots sanity |
| BR-081 | medium | unit_guess | «Дрель… **500 Wh**» → **`28.24.11.*`**, `unit` issue (confused **Wh** with power **W**) |
| BR-082 | high | csv_encoding | **UTF-16** CSV misread as **`cp1251`/`;`**, `header: false` → **3 garbage rows** / `not_found` |
| BR-083 | high | csv | Header row **`name,name`** not skipped → analyzed as product **`name,name`** (`not_found`) + comma-split data row → **31.01.12.110** |
| BR-084 | medium | numeric_parse | «рост **170 до 176**» → portal **`170` only** (same class as BR-060/BR-066) |

**CL01 JSON (official index):**

```json
{"text": "Костюм рабочий мужской размер 48-50 рост 170-176", "domain_hint": "clothing"}
```

**Actual:** `best_ktru.code` `14.12.10.000-00000002`, `card_status` `complete`, two portal characteristics only (see BR-052).

---

## Top 10 most damaging

1. **BR-052** — CL01 «complete» card with **zero KTRU characteristics** loaded for suit code (portal-only 2 fields).  
2. **BR-020** — Hand hammer + «18 В» → electric-tool KTRU with `ok`/`complete`.  
3. **BR-001** — Office desk + `domain_hint: tools` → machine-table 28.41 KTRU.  
4. **BR-055** — Guitar + tools hint → industrial «термокаталитическая установка».  
5. **BR-003** — CSV comma in name → conference table instead of writing desk.  
6. **BR-023** — Wardrobe + tools hint → window hardware 25.72.  
7. **BR-004 / BR-018 / BR-028** — `ok`+`complete` while «Рост» stays `new_property` (KTRU-only / minimal portal).  
8. **BR-026** — Bit/driver wording → kitchen knife set KTRU.  
9. **BR-006** — Rubber boots → metal-toe shoe code (H09).  
10. **BR-057** — Tonne unit silently treated as kilograms on hammer mass.

---

*Generated by red-team pass 2026-10-11 UTC. No application code was modified.*
