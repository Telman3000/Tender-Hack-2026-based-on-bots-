"""Fuzz /api/analyze; print anomalies (no auto-write to breaks.md)."""
from __future__ import annotations

import json
import random
import string
import urllib.request

BASE = "http://127.0.0.1:8000"


def post(body: dict) -> dict:
    req = urllib.request.Request(
        BASE + "/api/analyze",
        json.dumps(body, ensure_ascii=False).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main() -> None:
    anomalies = []
    base_products = [
        ("Стол письменный ЛДСП высота 750 мм", "furniture"),
        ("Костюм рабочий размер 48-50", "clothing"),
        ("Молоток слесарный 500 г", "tools"),
    ]
    for text, hint in base_products:
        for pad in ("", " " * 200, "\u200b", "\ufeff"):
            t = pad + text
            d = post({"text": t, "domain_hint": hint})
            if d["status"] == "ok" and d["card_status"] == "complete" and any(
                i["type"] == "new_property" for i in d.get("issues", [])
            ):
                anomalies.append(("complete+new", t[:40], d["best_ktru"]["code"]))
            if d["status"] == "ok" and not d.get("best_ktru"):
                anomalies.append(("ok_no_code", t[:40], None))
    # random garbage lengths
    for n in (0, 1, 5000, 20000):
        t = "Стол " + ("x" * n)
        try:
            d = post({"text": t, "domain_hint": "furniture"})
            ms = d.get("debug", {}).get("elapsed_ms", 0)
            if ms > 100 and n >= 5000:
                anomalies.append(("slow", n, ms))
        except Exception as e:
            anomalies.append(("exception", n, str(e)[:80]))
    # unit fuzz
    units = ["mm", "мм", "MM", "м", "km", "″", "ft", "lbs", "кг.", "гр", "ml", "mAh", "kW", "В", "W"]
    for u in units:
        d = post({"text": f"Стол письменный высота 750 {u}", "domain_hint": "furniture"})
        h = next((c for c in d["characteristics"] if "ысот" in c["name"].lower()), None)
        if d["status"] == "ok" and h and h.get("unit") == u:
            anomalies.append(("raw_unit_ok", u, h))
    print("ANOMALIES", len(anomalies))
    for a in anomalies[:40]:
        print(a)


if __name__ == "__main__":
    main()
