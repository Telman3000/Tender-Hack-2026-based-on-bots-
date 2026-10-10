"""Smoke test of a running server: API + UI.
Usage: python qa/smoke.py --base http://127.0.0.1:8000 --out ../qa_smoke
UI part needs `pip install playwright`; uses bundled Chromium, else system Edge/Chrome.
"""
from __future__ import annotations
import argparse, csv, json, time, urllib.error, urllib.request
from pathlib import Path

QA = Path(__file__).resolve().parent
IDS = ["CL01", "CL06", "CL13", "FU16", "FU21", "FU26", "FU30", "TO31", "TO36", "TO41"]
KEYS = {"input_text", "detected_domain", "product_guess", "characteristics", "issues",
        "narrowing", "best_ktru", "status", "next_steps"}


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


def api(base):
    cases = {c["id"]: c for c in csv.DictReader((QA / "cases.csv").open(encoding="utf-8-sig"))}
    out = []
    for i in IDS:
        c = cases[i]
        code, ms, body = post(base, {"text": c["query"], "domain_hint": c["category"]})
        try:
            j = json.loads(body); missing = sorted(KEYS - set(j)); st = j.get("status")
        except Exception:
            j, missing, st = None, ["<not json>"], None
        out.append({"id": i, "http": code, "ms": round(ms), "status": st, "missing_keys": missing,
                    "chars": len(j.get("characteristics", [])) if j else 0,
                    "best": (j.get("best_ktru") or {}).get("code") if j else None})
    # edge cases
    for name, p in [("empty_text", {"text": ""}), ("no_hint", {"text": "Стул офисный черный"}),
                    ("bad_hint", {"text": "Стул", "domain_hint": "cars"}),
                    ("long_text", {"text": "стол " * 2000})]:
        code, ms, body = post(base, p)
        out.append({"id": name, "http": code, "ms": round(ms), "body": body[:200].decode("utf-8", "replace")})
    return out


def ui(base, outdir):
    from playwright.sync_api import sync_playwright
    rep = {"console_errors": [], "page_errors": [], "shots": []}
    with sync_playwright() as p:
        b = None
        for kw in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
            try:
                b = p.chromium.launch(**kw); break
            except Exception:
                continue
        pg = b.new_page(viewport={"width": 1400, "height": 1000})
        pg.on("console", lambda m: m.type == "error" and rep["console_errors"].append(m.text))
        pg.on("pageerror", lambda e: rep["page_errors"].append(str(e)))
        pg.goto(base + "/", wait_until="networkidle")
        s = outdir / "01_initial.png"; pg.screenshot(path=str(s), full_page=True); rep["shots"].append(str(s))
        rep["demo_chips"] = pg.locator("#demos > *").count()
        for n, (text, dom) in enumerate([("Стол офисный ЛДСП высота 750 мм ширина 1200 мм цвет серый", "furniture"),
                                         ("Молоток", "tools"), ("Кастюм рабочий мужкой размер 48-50", "clothing")], 2):
            pg.fill("#text", text)
            try: pg.select_option("#domain", dom)
            except Exception: pass
            pg.click("#run")
            pg.wait_for_timeout(2500)
            s = outdir / f"0{n}_{dom}.png"; pg.screenshot(path=str(s), full_page=True); rep["shots"].append(str(s))
            r = pg.locator("#result")
            rep[f"q{n}"] = {"text": text, "status": pg.inner_text("#status")[:120],
                            "char_rows": r.locator("tr").count(), "badges": r.locator(".badge").count(),
                            "funnel": r.locator(".funnel").count()}
        # edit a characteristic value -> must trigger recalculation; description text should follow
        reqs = []
        pg.on("request", lambda r: "/api/analyze" in r.url and reqs.append(r.post_data))
        pg.fill("#text", "Стол офисный ЛДСП высота 750 мм ширина 1200 мм цвет серый"); pg.click("#run"); pg.wait_for_timeout(2500)
        before_res, n0 = pg.inner_text("#result"), len(reqs)
        v = pg.locator('#result [data-k="value"]').first
        old = v.input_value(); v.fill("900"); v.press("Tab"); pg.wait_for_timeout(3000)
        s = outdir / "05_after_edit.png"; pg.screenshot(path=str(s), full_page=True); rep["shots"].append(str(s))
        txt = pg.input_value("#text"); res_txt = pg.inner_text("#result")
        rep["edit"] = {"old_value": old, "new_value": "900", "recalc_requests": len(reqs) - n0,
                       "result_changed": before_res != res_txt, "textarea_after": txt,
                       "textarea_updated": "900" in txt, "result_still_has_750": "750" in res_txt,
                       "last_request": (reqs[-1] or "")[:300] if reqs else None}
        b.close()
    return rep


if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("--base", default="http://127.0.0.1:8000")
    a.add_argument("--out", default=str(QA / "smoke_out")); a.add_argument("--no-ui", action="store_true")
    o = a.parse_args(); out = Path(o.out); out.mkdir(parents=True, exist_ok=True)
    res = {"api": api(o.base)}
    if not o.no_ui:
        res["ui"] = ui(o.base, out)
    (out / "smoke.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
