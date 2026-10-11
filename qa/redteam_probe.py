"""Ad-hoc red-team probes against live /api/analyze. Run: python qa/redteam_probe.py [--base URL]"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def post(base: str, body: dict) -> tuple[int, dict | None, float]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base + "/api/analyze", data=data, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r), (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except Exception:
            d = {"detail": e.read().decode("utf-8", errors="replace")[:500]}
        return e.code, d, (time.perf_counter() - t0) * 1000


def code(d: dict | None) -> str:
    return ((d or {}).get("best_ktru") or {}).get("code") or ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    probes = [
        ("drill_power_unit", {"text": "Дрель-шуруповерт аккумуляторная мощность 10.8 Вт цвет серый", "domain_hint": "tools"}),
        ("drill_power_wrong", {"text": "Дрель-шуруповерт аккумуляторная мощность 10.8 В цвет серый", "domain_hint": "tools"}),
        ("hammer_kg", {"text": "Молоток слесарный масса 900 кг", "domain_hint": "tools"}),
        ("key_power", {"text": "Ключ гаечный 17х19 мм мощность 500 Вт", "domain_hint": "tools"}),
        ("rost_suit", {"text": "Костюм рабочий мужской размер 48-50 рост 170-176", "domain_hint": "clothing"}),
        ("cotton_pct", {"text": "Футболка хлопок 100% красная размер 48-50", "domain_hint": "clothing"}),
        ("bread_scope", {"text": "Хлеб пшеничный 500 г"}),
        ("car_scope", {"text": "Автомобиль легковой"}),
        ("office_chair_ok", {"text": "Стул офисный на колесах металл черный", "domain_hint": "furniture"}),
        ("table_ldsp", {"text": "Стол офисный ДСП высота 750 мм ширина 1200 мм глубина 600 мм цвет серый", "domain_hint": "furniture"}),
        ("typo_rubber", {"text": "Шпатель STAYER резиновый 150 мм", "domain_hint": "tools"}),
        ("typo_rubber_hammer", {"text": "Киянка резиновая TOPEX 680 гр", "domain_hint": "tools"}),
        ("jigsaw_weight_g", {"text": "Электролобзик Graphite 58G071 Вес 2.1 г", "domain_hint": "tools"}),
        ("fake_ktru_in_text", {"text": "31.01.10.000-00000099 стол письменный ЛДСП", "domain_hint": "furniture"}),
        ("ui_override", {
            "text": "Стол письменный",
            "domain_hint": "furniture",
            "characteristics": [{"name": "Высота", "value": "99999", "unit": "мм"}],
        }),
        ("synonym_mass", {"text": "Молоток слесарный масса 500 г", "domain_hint": "tools"}),
        ("synonym_weight", {"text": "Молоток слесарный вес 500 г", "domain_hint": "tools"}),
        ("cm_to_mm", {"text": "Ключ гаечный 17х19 мм длина 27 см цвет чорный", "domain_hint": "tools"}),
        ("negative_height", {"text": "Стол письменный высота -750 мм", "domain_hint": "furniture"}),
        ("zero_mass", {"text": "Молоток слесарный масса 0 г", "domain_hint": "tools"}),
        ("huge_text", {"text": "Стол " + "письменный " * 5000, "domain_hint": "furniture"}),
        ("zwj", {"text": "Сту\u200bл офисный черный", "domain_hint": "furniture"}),
        ("rtl", {"text": "\u202eСтол письменный\u202c ЛДСП", "domain_hint": "furniture"}),
        ("null_byte", {"text": "Стол\x00 письменный", "domain_hint": "furniture"}),
    ]
    for name, body in probes:
        s, d, ms = post(args.base, body)
        issues = [(i.get("type"), i.get("severity"), (i.get("message") or "")[:80]) for i in (d or {}).get("issues", [])[:5]]
        chars = [(c.get("name"), c.get("source"), c.get("value"), c.get("suspicious")) for c in (d or {}).get("characteristics", [])[:8]]
        print(f"\n=== {name} http={s} ms={ms:.0f} status={(d or {}).get('status')} code={code(d)} oos={(d or {}).get('out_of_scope')}")
        print("issues:", issues)
        print("chars:", chars)


if __name__ == "__main__":
    main()
