"""Round-6: numeric ranges, units, CSV edge, concurrency on CSV."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:8000"


def analyze(body: dict) -> dict:
    req = urllib.request.Request(
        BASE + "/api/analyze",
        json.dumps(body, ensure_ascii=False).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def csv_up(raw: bytes) -> dict:
    b = "----6"
    body = (
        f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"t.csv\"\r\n"
        f"Content-Type: text/csv\r\n\r\n"
    ).encode() + raw + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(
        BASE + "/api/analyze/csv",
        body,
        {"Content-Type": f"multipart/form-data; boundary={b}"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def main() -> None:
    unit_cases = [
        ("wh_vs_w", "Дрель аккумуляторная мощность 500 Wh", "tools"),
        ("ml_cyr", "Клей канцелярский объём 40 мл", "tools"),
        ("ml_lat", "Клей канцелярский объём 40 ml", "tools"),
        ("range_mm_en_dash", "Стол письменный 1200–750 мм", "furniture"),
        ("range_to", "Костюм рабочий рост 170 до 176", "clothing"),
        ("approx", "Стол письменный высота около 750 мм", "furniture"),
        ("plusminus", "Стол письменный ширина 1200±50 мм", "furniture"),
    ]
    for label, text, hint in unit_cases:
        d = analyze({"text": text, "domain_hint": hint})
        bk = (d.get("best_ktru") or {}).get("code", "—")
        iss = [i["type"] for i in d.get("issues", [])][:3]
        print(f"{label}\t{d['status']}\t{bk}\t{iss}")

    # CSV: UTF-16 LE BOM
    raw = "name\nСтол письменный\n".encode("utf-16-le")
    raw = b"\xff\xfe" + raw[2:] if not raw.startswith(b"\xff\xfe") else raw
    try:
        cd = csv_up(raw)
        r0 = cd["results"][0]
        inner = r0.get("result") or r0
        bk = (inner.get("best_ktru") or {}) if isinstance(inner, dict) else {}
        print("csv_utf16", cd["file"], bk.get("code"), r0.get("error"))
    except urllib.error.HTTPError as e:
        print("csv_utf16", e.code, e.read()[:120])

    # CSV: duplicate column header row in file
    raw2 = "name,name\nСтол,письменный\n".encode("utf-8")
    cd = csv_up(raw2)
    print("csv_dup_col_header", cd["file"], cd["results"][0].get("text"), cd["results"][0].get("error"))

    # concurrent CSV uploads x5
    raw3 = "name\nСтол письменный\n".encode("utf-8")

    def one(_):
        return csv_up(raw3)["summary"]["elapsed_ms"]

    t0 = time.perf_counter()
    with ThreadPoolExecutor(5) as ex:
        ms = list(ex.map(one, range(5)))
    print("concurrent_csv5", f"wall={(time.perf_counter()-t0)*1000:.0f}", f"rows_ms={ms}")


if __name__ == "__main__":
    main()
