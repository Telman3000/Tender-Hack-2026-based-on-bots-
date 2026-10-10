"""Batch tab check in a real browser.
python qa/ui_batch.py --base http://127.0.0.1:8815 --out <dir> file1.csv [file2.csv ...]
For each file: upload in 'Пакетная проверка', wait for completion, time end-to-end, compare each row's code with a direct
/api/analyze call for the same text, check export CSV, XSS (dialogs/injected nodes), console errors, layout overflow.
"""
from __future__ import annotations
import argparse, csv, io, json, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright


def api(base, text):
    req = urllib.request.Request(base + "/api/analyze", json.dumps({"text": text}).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            d = json.load(r); return (d.get("best_ktru") or {}).get("code", "")
    except urllib.error.HTTPError as e:
        return f"HTTP{e.code}"


def main():
    a = argparse.ArgumentParser(); a.add_argument("--base"); a.add_argument("--out"); a.add_argument("files", nargs="+"); o = a.parse_args()
    out = Path(o.out); out.mkdir(parents=True, exist_ok=True); rep = {}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge"); ctx = b.new_context(viewport={"width": 1280, "height": 1000}, accept_downloads=True)
        pg = ctx.new_page(); errs, dialogs, fails = [], [], []
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text)); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        pg.on("response", lambda r: r.status >= 400 and fails.append(f"{r.status} {r.url}"))
        for fn in o.files:
            pg.goto(o.base + "/", wait_until="networkidle"); pg.click("#tabBatch")
            e0, d0, f0 = len(errs), len(dialogs), len(fails)
            t = time.perf_counter()
            pg.set_input_files("#csvFile", fn)
            pg.wait_for_function("() => !document.querySelector('#exportCsv').disabled", timeout=120000)
            wall = time.perf_counter() - t
            k = window = pg.evaluate("() => ({n: window.__ktru.batch.results.length, items: window.__ktru.batch.items.map(x=>x.text), codes: window.__ktru.batch.results.map(r => r && (r.code || (r.error ? 'ERR:' + r.error : ''))), total: window.__ktru.batch.total_ms, mode: document.querySelector('#batchMode').textContent})")
            inj = pg.evaluate("() => document.querySelectorAll('#batchBody script, #batchBody img').length")
            name = Path(fn).stem; pg.screenshot(path=str(out / f"batch_{name}.png"), full_page=True)
            with pg.expect_download() as dl:
                pg.click("#exportCsv")
            exp = dl.value.path(); raw = open(exp, "rb").read().decode("utf-8-sig")
            exp_rows = list(csv.reader(io.StringIO(raw), delimiter=";"))
            mism = []
            for i, (txt, code) in enumerate(zip(k["items"], k["codes"])):
                c2 = api(o.base, txt)
                if (code or "") != (c2 or ""):
                    mism.append((i + 1, txt[:50], code, c2))
            # click a row -> opens in editor
            pg.locator("#batchBody tr").first.click(); pg.wait_for_timeout(2500)
            opened = pg.input_value("#text")
            ov = pg.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
            rep[name] = dict(rows=k["n"], first=k["items"][:1], wall_s=round(wall, 1), total_ms=k["total"], mode=k["mode"], mismatches=mism[:10],
                             n_mismatch=len(mism), export_rows=len(exp_rows), injected=inj, dialogs=dialogs[d0:], js_errors=errs[e0:],
                             http_fail=sorted(set(fails[f0:]))[:5], row_click_opens=opened[:60], h_overflow=ov)
            print(name, json.dumps(rep[name], ensure_ascii=False))
        for w in (1280, 420):
            pg.set_viewport_size({"width": w, "height": 1000})
            for tab in ("#tabSingle", "#tabBatch"):
                pg.click(tab); pg.wait_for_timeout(500)
                ov = pg.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
                pg.screenshot(path=str(out / f"layout_{w}_{tab[4:]}.png"), full_page=True); print("layout", w, tab, "scrollWidth/innerWidth", ov)
        b.close()


if __name__ == "__main__":
    main()
