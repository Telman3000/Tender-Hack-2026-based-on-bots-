"""Быстрый прогон API и экрана.

    python qa/smoke.py --base http://127.0.0.1:8000
    python qa/smoke.py --base http://127.0.0.1:8000 --no-ui
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

QA = Path(__file__).resolve().parent
IDS = ["CL01", "CL06", "CL13", "FU16", "FU21", "FU26", "FU30", "TO31", "TO36", "TO41"]
KEYS = {"input_text", "detected_domain", "product_guess", "characteristics", "issues", "narrowing",
        "best_ktru", "status", "next_steps", "match_status", "card_status", "search", "checks", "question"}
TABLE_TEXT = "Стол офисный ЛДСП высота 750 мм ширина 1200 мм цвет серый"


def post(base, payload):
    req = urllib.request.Request(base + "/api/analyze", json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            code, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read()
    return code, (time.perf_counter() - t) * 1000, body


def api(base, problems):
    cases = {c["id"]: c for c in csv.DictReader((QA / "cases.csv").open(encoding="utf-8-sig"))}
    out = []
    for i in IDS:
        c = cases.get(i)
        if not c:
            continue
        code, ms, body = post(base, {"text": c["query"], "domain_hint": c["category"]})
        try:
            j = json.loads(body)
            missing = sorted(KEYS - set(j))
        except Exception:
            j, missing = None, ["<не JSON>"]
        if code >= 500 or missing:
            problems.append(f"{i}: HTTP {code}, нет полей {missing}")
        out.append({"id": i, "http": code, "ms": round(ms), "missing_keys": missing,
                    "match_status": j.get("match_status") if j else None, "card_status": j.get("card_status") if j else None,
                    "search": {k: v for k, v in (j.get("search") or {}).items() if k != "shortlist"} if j else None,
                    "best": (j.get("best_ktru") or {}).get("code") if j else None})
    for name, payload, want in [("empty_text", {"text": ""}, 422), ("bad_hint", {"text": "Стул", "domain_hint": "cars"}, 422),
                                ("no_hint", {"text": "Стул офисный черный"}, 200), ("long_text", {"text": "стол " * 2000}, 200)]:
        code, ms, body = post(base, payload)
        if code != want:
            problems.append(f"{name}: HTTP {code}, ожидался {want}")
        out.append({"id": name, "http": code, "ms": round(ms)})
    return out


def ui(base, outdir, problems):
    from playwright.sync_api import sync_playwright
    rep = {"js_errors": []}
    with sync_playwright() as p:
        b = None
        for kw in ({}, {"channel": "chrome"}, {"channel": "msedge"}):
            try:
                b = p.chromium.launch(**kw)
                break
            except Exception:
                continue
        if b is None:
            problems.append("нет Chromium для проверки экрана")
            return rep
        pg = b.new_page(viewport={"width": 1440, "height": 1000})
        pg.on("console", lambda m: m.type == "error" and rep["js_errors"].append(m.text))
        pg.on("pageerror", lambda e: rep["js_errors"].append(str(e)))
        requests = []
        pg.on("request", lambda r: "/api/analyze" in r.url and requests.append(r.post_data))

        def settle(text):
            pg.wait_for_function(
                "(t) => !document.getElementById('status').className.includes('busy') && document.getElementById('hl').textContent.trim() === t",
                arg=text, timeout=20000)
            pg.wait_for_timeout(150)

        pg.goto(base + "/", wait_until="networkidle")
        rep["demo_chips"] = pg.locator("#demos > button").count()
        for n, (text, dom) in enumerate([(TABLE_TEXT, "furniture"), ("Молоток", "tools"),
                                         ("Кастюм рабочий мужкой размер 48-50", "clothing")], 1):
            pg.fill("#text", text)
            pg.select_option("#domain", dom)
            pg.click("#run")
            settle(text)
            pg.screenshot(path=str(outdir / f"0{n}_{dom}.png"), full_page=True)
            r = pg.locator("#result")
            row = {"status": pg.inner_text("#status"), "badges": r.locator(".sbadge").count(),
                   "counters": r.locator("#counters .counter").count(), "rows": r.locator("tr[data-row]").count()}
            rep[text] = row
            if row["badges"] != 2 or row["counters"] != 3:
                problems.append(f"«{text}»: бейджей {row['badges']}, счётчиков {row['counters']}")
        pg.fill("#text", TABLE_TEXT)
        pg.select_option("#domain", "furniture")
        pg.click("#run")
        settle(TABLE_TEXT)
        before = len(requests)
        cell = pg.locator('#chars tr[data-name="высота"] [data-k="value"]')
        if cell.count():
            cell.fill("900")
            cell.press("Tab")
            edited = TABLE_TEXT.replace("750", "900")
            settle(edited)
            rep["table_edit"] = {"requests": len(requests) - before, "text": pg.input_value("#text"),
                                 "undo_enabled": pg.locator("#undo").is_enabled()}
            if pg.input_value("#text") != edited:
                problems.append("правка в таблице не попала в текст")
            pg.click("#undo")
            settle(TABLE_TEXT)
            rep["table_edit"]["after_undo"] = pg.input_value("#text")
            if pg.input_value("#text") != TABLE_TEXT:
                problems.append("«Отменить правку» не вернула текст после правки в таблице")
        else:
            problems.append("нет строки «Высота» в таблице")
        b.close()
    if rep["js_errors"]:
        problems.append(f"ошибки JavaScript: {rep['js_errors'][:3]}")
    return rep


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--base", default="http://127.0.0.1:8000")
    a.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "ste_smoke"))
    a.add_argument("--no-ui", action="store_true")
    o = a.parse_args()
    out = Path(o.out)
    out.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    res = {"api": api(o.base.rstrip("/"), problems)}
    if not o.no_ui:
        res["ui"] = ui(o.base.rstrip("/"), out, problems)
    res["problems"] = problems
    (out / "smoke.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print("\nOK" if not problems else f"\nПроблем: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
