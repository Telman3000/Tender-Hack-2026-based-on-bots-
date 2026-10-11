# Red-team breaks (KTRU matching / `POST /api/analyze`)

**Branch:** `cursor/red-team-ktru-breaks-3b39`  
**Environment:** `catalog.db` built 2026-10-11 from `_materials/` (see Setup). Server: `uvicorn app.main:app` on `127.0.0.1:8000`.

## Setup (repro)

1. **Materials:** Official archive https://disk.yandex.ru/d/5Olg3IoYYf4loA was **unavailable** from the cloud agent (Yandex Disk 500 / captcha). Fallback used:
   - Downloaded 82 `nsiKTRUs_all_*.xml.zip` parts from the public EIS mirror `keysystems.ru` into `_materials/ktru_parts/`.
   - Built hackathon-shaped `КТРУ/КТРУ xml.zip` via `python scripts/assemble_materials_from_mirror.py` (renames XML to `*all_actual*` for `build_index`).
   - **Portal XLSX exports were not obtained** → `portal_ste=0`, `portal_chars=0` in `catalog.db` (3030 KTRU rows). Breaks involving `source: "portal"` are still valid on API semantics.
2. `python -m scripts.build_index --materials _materials`
3. `uvicorn app.main:app --host 127.0.0.1 --port 8000`

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

## Count by severity

| severity | count |
|----------|------:|
| critical | 2 |
| high | 6 |
| medium | 9 |
| low | 1 |
| **total** | **18** |

## Top 10 most damaging

1. **BR-001** — Wrong KTRU (machine table) for office desk via `domain_hint: tools`.  
2. **BR-003** — CSV comma name → wrong furniture KTRU (conference table).  
3. **BR-004** — Declares `ok` + `complete` card with invented «Рост».  
4. **BR-006** — Wrong footwear KTRU for rubber boots (H09).  
5. **BR-007** — Wrong халат line (14.14 vs 14.12) on minimal query.  
6. **BR-002** — Misleading `not_found` instead of out-of-scope on domain abuse.  
7. **BR-005** — Fabric composition as NEW property with `status=ok`.  
8. **BR-008** — Demo drill power 10.8 W accepted without sanity check.  
9. **BR-009** — Dangerous typo suggestion (rubber → gasoline).  
10. **BR-011** — Nonsense auto-fix suggestion (99999 см).

*(BR-017 typo miss and BR-018 CL01 complete+new are additional high/medium findings.)*

---

*Generated by red-team pass 2026-10-11 UTC. No application code was modified.*
