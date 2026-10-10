"""UI acceptance: table edit -> request/response/text sync, reset button, not_found label.
Usage: python qa/ui_accept.py --base http://127.0.0.1:8000 --out ../qa_smoke/ui
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from playwright.sync_api import sync_playwright

TEXT = "Стол офисный ЛДСП высота 750 мм ширина 1200 мм цвет серый"


def norm(s):  # ignore the latency label ("Распознано · 87 мс")
    return re.sub(r"\d+(\.\d+)?\s*мс", "<ms>", s)


def launch(p):
    for kw in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
        try:
            return p.chromium.launch(**kw)
        except Exception:
            continue
    raise RuntimeError("no browser")


def hrow(pg):
    """Value cell of the «Высота» row (row order differs between UI versions)."""
    i = pg.evaluate("() => [...document.querySelectorAll('#result [data-k=name]')].findIndex(e => e.value === 'Высота')")
    return pg.locator('#result [data-k="name"]').nth(max(i, 0)).locator("xpath=ancestor::tr").locator('[data-k="value"]')


def main(base, out):
    out.mkdir(parents=True, exist_ok=True)
    rep, errs, calls = {}, [], []
    with sync_playwright() as p:
        b = launch(p); pg = b.new_page(viewport={"width": 1400, "height": 1000})
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("response", lambda r: "/api/analyze" in r.url and calls.append((r.request.post_data, r)))
        shot = lambda n: pg.screenshot(path=str(out / n), full_page=True)
        pg.goto(base + "/", wait_until="networkidle")
        pg.fill("#text", TEXT); pg.select_option("#domain", "furniture"); pg.click("#run"); pg.wait_for_timeout(2500)
        shot("01_initial_result.png")
        res0 = pg.inner_text("#result")
        h = hrow(pg)
        rep["first_value"] = h.input_value()
        n = len(calls); h.fill("900"); h.press("Tab"); pg.wait_for_timeout(3000)
        shot("02_after_edit_900.png")
        req, resp = (calls[-1] if len(calls) > n else (None, None))
        body = json.loads(req) if req else {}
        rj = resp.json() if resp else {}
        rep["edit"] = {
            "recalc_requests": len(calls) - n,
            "request_chars_has_900": any(c.get("value") == "900" for c in body.get("characteristics", [])),
            "request_text": body.get("text"),
            "response_has_900": any(str(c.get("value")) == "900" for c in rj.get("characteristics", [])),
            "response_input_text": rj.get("input_text"),
            "table_value_after": hrow(pg).input_value(),
            "textarea_after": pg.input_value("#text"),
        }
        rep["edit"]["text_synced"] = "900" in rep["edit"]["textarea_after"] and "750" not in rep["edit"]["textarea_after"]
        rep["edit"]["note"] = pg.locator("#ovNote").inner_text() if pg.locator("#ovNote").count() else None
        # reset
        btn = pg.locator("#resetOv")
        rep["reset_button_visible"] = btn.count() > 0
        if btn.count():
            n = len(calls); btn.click(); pg.wait_for_timeout(3000); shot("03_after_reset.png")
            res1 = pg.inner_text("#result")
            val = hrow(pg).input_value(); txt = pg.input_value("#text")
            last = calls[-1][1].json() if len(calls) > n else {}
            rep["reset"] = {"requests": len(calls) - n, "value_restored": val, "textarea": txt,
                            "response_input_text": last.get("input_text"),
                            "result_equals_initial": norm(res1) == norm(res0),
                            "note_gone": pg.locator("#ovNote").count() == 0}
            rep["reset"]["PASS"] = (val == rep["first_value"] and txt == TEXT and norm(res1) == norm(res0))
        # not_found label
        pg.fill("#text", TEXT); pg.select_option("#domain", "clothing"); pg.click("#run"); pg.wait_for_timeout(2500)
        shot("04_not_found.png")
        st = pg.inner_text("#status")
        rep["not_found"] = {"status_banner": st, "api_status": (calls[-1][1].json() or {}).get("status"),
                            "label_ok": "Товар не распознан" in st, "raw_leak": "not_found" in pg.inner_text("body")}
        # general: badges / funnel on a normal query
        pg.fill("#text", "Дрель ударная мощность 650 Вт масса 3.2 кг"); pg.select_option("#domain", "tools"); pg.click("#run"); pg.wait_for_timeout(2500)
        shot("05_tools.png")
        r = pg.locator("#result")
        rep["general"] = {"badges": r.locator(".badge").count(), "funnel": r.locator(".funnel").count(), "rows": r.locator("tr").count()}
        fav = pg.request.get(base + "/favicon.ico"); rep["favicon_status"] = fav.status
        rep["favicon_link"] = pg.evaluate("() => [...document.querySelectorAll('link[rel*=icon]')].map(l => l.href)")
        b.close()
    rep["js_errors"] = errs
    (out / "ui_accept.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("--base", default="http://127.0.0.1:8000"); a.add_argument("--out", default="qa/ui_out")
    o = a.parse_args(); main(o.base, Path(o.out))
