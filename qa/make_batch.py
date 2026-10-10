"""Build batch test CSVs: qa/batch100.csv (utf-8, ';', header) + variants in _out."""
import csv, sys
from pathlib import Path
QA = Path(r"C:\Users\Asus\Desktop\Vtoroy_work\wt-qa\qa"); OUT = Path(sys.argv[1])
q = [r["query"] for r in csv.DictReader((QA/"cases.csv").open(encoding="utf-8-sig"))]
q += [r["query"] for r in csv.DictReader((QA/"holdout.csv").open(encoding="utf-8-sig"))]
L = "Стол письменный ЛДСП 1200х600х750 мм цвет бук. "
broken = ["asdkjh qweoiu zxcmnb", "😀😀😀🔥", "<script>alert(1)</script> стул офисный", "<img src=x onerror=alert(2)>",
          "Хлеб пшеничный нарезной 500 г", "' OR 1=1 --", L*200, "Стол письменный высота -750 мм",
          "Ключ гаечный разводной мощность 100 Вт", "Стул \"Венский\" деревянный"]
rows = q + broken
# utf-8, ';' with header and blank lines (blank lines must be skipped -> still 100)
with (QA/"batch100.csv").open("w", encoding="utf-8", newline="") as f:
    f.write("Наименование\n")
    for i, r in enumerate(rows):
        f.write('"' + r.replace('"', '""') + '"\n' if (";" in r or '"' in r) else r + "\n")
        if i in (10, 50): f.write("\n   \n")
# cp1251, ',' all quoted, header 'name' (emoji are not representable in cp1251 -> replaced)
with (OUT/"batch100_cp1251_comma.csv").open("w", encoding="cp1251", errors="replace", newline="") as f:
    f.write('"name"\r\n')
    for r in rows: f.write('"' + r.replace('"', '""') + '"\r\n')
# utf-8 BOM, no header, unquoted
with (OUT/"batch100_bom_noheader.csv").open("w", encoding="utf-8-sig", newline="") as f:
    for r in rows: f.write(r.replace("\n", " ") + "\n")
print(len(rows))
