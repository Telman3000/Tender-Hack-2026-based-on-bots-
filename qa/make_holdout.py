"""Build qa/holdout.csv from portal exports (catalog.db portal_ste) + ACTIVE KTRU names.
GT = OKPD2 prefixes of ACTIVE KTRU positions whose name matches the product type (checked in KTRU XML subset).
Usage: python qa/make_holdout.py <catalog.db> <ktru_active_subset.json>
"""
import csv, json, random, re, sqlite3, sys
from pathlib import Path

QA = Path(__file__).resolve().parent
db, subset = sys.argv[1], sys.argv[2]
A = [x for x in json.load(open(subset, encoding="utf-8")) if x["status"] == "ACTIVE"]
# (domain, portal name regex, exact ACTIVE KTRU names, n_clean, n_incomplete, incomplete query)
MAP = [
 ("clothing", r"^Брюки ", ["Брюки"], 1, 1, "Брюки"),
 ("clothing", r"^Сорочка мужск", ["Сорочка мужская"], 1, 0, None),
 ("clothing", r"^Фартук (?!.*(Winx|детск|Детск))", ["Фартук профессиональный"], 1, 1, "Фартук"),
 ("clothing", r"^Жакет ", ["Жакет женский"], 1, 0, None),
 ("clothing", r"^Кроссовки ", ["Кроссовки"], 1, 1, "Кроссовки"),
 ("clothing", r"^Сапоги резинов", ["Сапоги резиновые формовые"], 1, 0, None),
 ("clothing", r"^Блузка ", ["Блузка женская"], 1, 1, "Блузка"),
 ("clothing", r"^Перчатки трикотаж", ["Перчатки трикотажные для защиты от внешних воздействий"], 1, 1, "Перчатки трикотажные"),
 ("clothing", r"^Шорты ", ["Шорты"], 1, 1, "Шорты"),
 ("furniture", r"^Тумба .*прикроват", ["Тумба прикроватная"], 1, 0, None),
 ("furniture", r"^Диван ", ["Диван"], 1, 1, "Диван"),
 ("furniture", r"^Вешалка ", ["Вешалка металлическая"], 1, 1, "Вешалка"),
 ("furniture", r"^Кровать ", ["Кровать для взрослых бытового назначения", "Кровать детская"], 1, 1, "Кровать"),
 ("furniture", r"^Банкетка ", ["Банкетка"], 1, 0, None),
 ("furniture", r"^Табурет ", ["Табурет"], 1, 1, "Табурет"),
 ("furniture", r"^Полка ", ["Полка навесная"], 1, 0, None),
 ("furniture", r"^Витрина ", ["Витрина"], 1, 1, "Витрина"),
 ("furniture", r"^Стол компьютерн", ["Стол компьютерный"], 1, 1, "Стол компьютерный"),
 ("tools", r"^Электролобзик ", ["Электролобзик"], 1, 1, "Электролобзик"),
 ("tools", r"^Шуруповерт ", ["Шуруповерт"], 1, 1, "Шуруповерт"),
 ("tools", r"^Струбцина ", ["Струбцина"], 1, 1, "Струбцина"),
 ("tools", r"^Тиски ", ["Тиски слесарные"], 1, 0, None),
 ("tools", r"^Клещи (?!.*(токоизмер|мультим))", ["Клещи"], 1, 1, "Клещи"),
 ("tools", r"^Молоток (?!отбой)", ["Молоток"], 1, 0, None),
 ("tools", r"^Шпатель ", ["Шпатель"], 1, 1, "Шпатель"),
 ("tools", r"^Стамеска ", ["Стамеска"], 1, 0, None),
 ("tools", r"^Киянка ", ["Киянка"], 1, 1, "Киянка"),
]
EXCL = ["Дебют", "КБС-011", "Протон", "УНИВЕРСАЛ", "Аляска", "л08-КБР", "Вилора", "ОФИСМАГ", "Профи", "Makita HM",
        "Bort BAS", "17х19", "SPARTA", "PSB 650", "Техсервис", "AFC-02", "ЛАЙМА", "LAIMA", "Лига"]
c = sqlite3.connect(db); rnd = random.Random(2026)
rows, n = [], 0
for dom, rx, knames, nc, ni, iq in MAP:
    pos = [x for x in A if x["name"].strip() in knames]
    assert pos, knames
    prefixes = sorted({x["code"].split("-")[0] for x in pos})
    items = [r for r in c.execute("select ste_id,name,chars_raw from portal_ste where domain=? and chars_raw<>''", (dom,))
             if re.search(rx, r[1]) and not any(e in r[1] for e in EXCL)]
    assert items, rx
    rnd.shuffle(items)
    for ste, name, chars in items[:nc]:
        parts = [p.strip() for p in (chars or "").split("|") if p.strip() and not re.search(r"упаковк|\(не задано\)|Комплектац", p)]
        q = re.sub(r"\s+", " ", name.strip()) + (" " + " ".join(parts[:3]) if parts else "")
        n += 1; rows.append([f"H{n:02d}", dom, "clean", q, "|".join(prefixes), "ok|ambiguous|need_more",
                             f"portal ste_id={ste}; ACTIVE KTRU: {', '.join(knames)}"])
    for _ in range(ni):
        n += 1; rows.append([f"H{n:02d}", dom, "incomplete", iq, "|".join(prefixes), "need_more|ambiguous",
                             f"type only; ACTIVE KTRU: {', '.join(knames)}"])
with open(QA / "holdout.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f); w.writerow(["id", "category", "type", "query", "expected_code", "expected_status", "comment"]); w.writerows(rows)
print(len(rows))
