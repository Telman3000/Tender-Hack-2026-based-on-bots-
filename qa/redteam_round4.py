"""Round-4: categories, CSV encodings, concurrency, version codes, duplicates."""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "http://127.0.0.1:8000"


def analyze(body: dict) -> dict:
    req = urllib.request.Request(
        BASE + "/api/analyze",
        json.dumps(body, ensure_ascii=False).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def csv_raw(raw: bytes) -> dict:
    b = "----r4"
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


def flag(label: str, why: str, detail: str) -> None:
    print(f"FLAG\t{label}\t{why}\t{detail[:200]}")


def main() -> None:
    # --- wrong domain / category ---
    probes = [
        ("food_furniture", {"text": "Консервы мясные говядина 325 г", "domain_hint": "furniture"}),
        ("medicine_clothing", {"text": "Парацетамол таблетки 500 мг упаковка 20", "domain_hint": "clothing"}),
        ("tire_tools", {"text": "Шина автомобильная 205/55 R16", "domain_hint": "tools"}),
        ("book_furniture", {"text": "Учебник математики 5 класс", "domain_hint": "furniture"}),
        ("software_tools", {"text": "Лицензия Microsoft Windows 11 Pro", "domain_hint": "tools"}),
    ]
    for label, body in probes:
        d = analyze(body)
        bk = d.get("best_ktru") or {}
        if d.get("status") in ("ok", "ambiguous", "need_more") and bk.get("code"):
            flag(label, "matched_wrong_scope", f"{bk.get('code')} {bk.get('name')[:50]}")
        elif d.get("status") == "not_found" and not d.get("out_of_scope"):
            flag(label, "not_found_no_oos", str(d.get("status")))

    # --- version / duplicate codes in candidates ---
    d = analyze({"text": "Стол письменный ЛДСП", "domain_hint": "furniture"})
    cands = [c.get("code") for c in d.get("candidates", [])[:5]]
    bk = (d.get("best_ktru") or {}).get("code")
    if bk and cands and any("00000006" in x for x in cands) and "00000004" in (bk or ""):
        flag("desk_version", "older_top1", f"best={bk} cands={cands}")

    # --- CSV: pipe inside quotes, escaped quotes, null bytes ---
    csv_tests = [
        ("pipe_quoted", 'name\n"Стол | письменный | ЛДСП"\n'.encode("utf-8")),
        ("escaped_quote", 'name\n"Стол ""офисный"" письменный"\n'.encode("utf-8")),
        ("semicolon_utf8", "name;product\nСтол; письменный\n".encode("utf-8")),
        ("wrong_header_ru", "наименование\nСтол письменный\n".encode("utf-8")),
        ("duplicate_lines", "name\nСтол письменный\nСтол письменный\n".encode("utf-8")),
    ]
    for label, raw in csv_tests:
        try:
            cd = csv_raw(raw)
            r0 = cd["results"][0]
            inner = r0.get("result") or r0
            if r0.get("error"):
                flag(f"csv_{label}", "row_error", r0["error"])
                continue
            bk = (inner.get("best_ktru") or {}) if isinstance(inner, dict) else {}
            code = bk.get("code", "")
            if label == "wrong_header_ru" and inner.get("status") != "not_found":
                flag(f"csv_{label}", "accepted_without_name_col", code)
            if "12.110" in code and "письмен" in str(r0.get("text", "")).lower():
                flag(f"csv_{label}", "wrong_desk", code)
        except urllib.error.HTTPError as e:
            flag(f"csv_{label}", f"http_{e.code}", e.read()[:120].decode("utf-8", errors="replace"))

    # --- concurrency: same CL01 50x ---
    body = {
        "text": "Костюм рабочий мужской размер 48-50 рост 170-176",
        "domain_hint": "clothing",
    }

    def one(_: int) -> tuple[int, str]:
        d = analyze(body)
        return len(d.get("characteristics", [])), d.get("card_status", "")

    t0 = time.perf_counter()
    with ThreadPoolExecutor(50) as ex:
        rows = list(ex.map(one, range(50)))
    wall = (time.perf_counter() - t0) * 1000
    char_counts = {r[0] for r in rows}
    if char_counts != {2}:
        flag("cl01_concurrent", "char_count_drift", str(char_counts))
    if wall > 5000:
        flag("cl01_concurrent", "slow_50", f"{wall:.0f}ms")

    # --- mixed lookalikes Cyrillic/Latin in brand ---
    d = analyze({"text": "Костюм рабочий АНЦ АНС размер 50", "domain_hint": "clothing"})
    if d.get("status") == "ok" and d.get("card_status") == "complete" and len(d.get("characteristics", [])) <= 2:
        flag("cl01_variant", "complete_thin_card", str(len(d.get("characteristics", []))))

    # --- unit edge: micro, percent, fraction unicode ---
    for label, text in [
        ("frac_half", "Стол письменный высота ½ м"),
        ("percent", "Футболка хлопок 100％ размер 52"),
        ("unit_kg_dot", "Молоток слесарный 0,5 кг"),
    ]:
        d = analyze({"text": text, "domain_hint": "tools" if "Молоток" in text else "clothing"})
        issues = [i.get("type") for i in d.get("issues", [])]
        bk = (d.get("best_ktru") or {}).get("code", "")
        flag(label, d.get("status", ""), f"code={bk} issues={issues[:5]}")

    print("DONE round4")


if __name__ == "__main__":
    main()
