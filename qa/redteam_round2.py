"""Round-2 red-team probes: CSV, unicode, units, concurrency."""
from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:8000"


def analyze(body: dict) -> tuple[int, dict | None, float]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + "/api/analyze", data=data, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r), (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except Exception:
            d = {"detail": e.read().decode("utf-8", errors="replace")[:400]}
        return e.code, d, (time.perf_counter() - t0) * 1000


def csv_upload(raw: bytes, filename: str = "t.csv") -> tuple[int, dict | None, float]:
    boundary = "----redteam"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8") + raw + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/analyze/csv",
        body,
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.load(r), (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except Exception:
            d = {"detail": e.read()[:400].decode("utf-8", errors="replace")}
        return e.code, d, (time.perf_counter() - t0) * 1000


def main() -> None:
    probes = [
        ("homoglyph_latin_a", {"text": "Stol pismennyi LDSP vysota 750 mm", "domain_hint": "furniture"}),
        ("greek_omicron", {"text": "Ст\u03bfл письменный ЛДСП", "domain_hint": "furniture"}),
        ("german_mixed", {"text": "Schreibtisch стол офисный 1200mm", "domain_hint": "furniture"}),
        ("inch_units", {"text": "Стол письменный ширина 47 дюймов", "domain_hint": "furniture"}),
        ("scientific", {"text": "Стол письменный высота 7.5e2 мм", "domain_hint": "furniture"}),
        ("thin_space_num", {"text": "Стол письменный ширина 1\u2009200 мм", "domain_hint": "furniture"}),
        ("duplicate_chars", {
            "text": "Молоток слесарный",
            "domain_hint": "tools",
            "characteristics": [
                {"name": "Масса молотка", "value": "500", "unit": "г"},
                {"name": "Масса молотка", "value": "900", "unit": "г"},
            ],
        }),
        ("conflict_chars", {
            "text": "Стол письменный",
            "domain_hint": "furniture",
            "characteristics": [
                {"name": "Вид материала столешницы", "value": "ЛДСП", "unit": None},
                {"name": "Вид материала столешницы", "value": "Стекло", "unit": None},
            ],
        }),
        ("mah_battery", {"text": "Дрель аккумуляторная 18 В емкость 2000 mAh", "domain_hint": "tools"}),
        ("kw_power", {"text": "Шуруповерт сетевой мощность 0.65 kW", "domain_hint": "tools"}),
        ("percent_cotton", {"text": "Футболка хлопок 100% размер 52", "domain_hint": "clothing"}),
        ("food_furniture", {"text": "Стол кухонный для пиццы 1200 мм", "domain_hint": "furniture"}),
        ("toy_scope", {"text": "Мягкая игрушка медведь 30 см", "domain_hint": None}),
        ("medical_scope", {"text": "Каталка медицинская для пациентов", "domain_hint": "furniture"}),
    ]
    for name, body in probes:
        s, d, ms = analyze(body)
        code = ((d or {}).get("best_ktru") or {}).get("code", "")
        print(f"{name}: http={s} ms={ms:.0f} code={code} status={(d or {}).get('status')} oos={(d or {}).get('out_of_scope')}")

    csv_tests = [
        ("utf8_bom", "\ufeffname\nСтол письменный\n".encode("utf-8-sig")),
        ("cp1251_semi", "наименование;Стол письменный\n".encode("cp1251")),
        ("tab_id", "id\tнаименование\n1\tСтол письменный\n".encode("utf-8")),
        ("quoted_comma", 'name\n"Стол, письменный, ЛДСП"\n'.encode("utf-8")),
        ("dup_rows", "name\nСтол письменный\nСтол письменный\n".encode("utf-8")),
        ("empty_lines", "name\n\nСтол письменный\n\n".encode("utf-8")),
    ]
    for name, raw in csv_tests:
        s, d, ms = csv_upload(raw)
        info = (d or {}).get("file") or (d or {}).get("detail")
        r0 = ((d or {}).get("results") or [{}])[0]
        code = ((r0.get("best_ktru") or {}) if isinstance(r0, dict) else {}).get("code", r0.get("error", ""))
        print(f"CSV {name}: http={s} ms={ms:.0f} file={info} first={code}")


if __name__ == "__main__":
    main()
