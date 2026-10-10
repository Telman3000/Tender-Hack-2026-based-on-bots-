"""'Break the solution' run against a live server.
python qa/run_break.py --base http://127.0.0.1:8814  -> qa/break_results.csv, PASS/FAIL per case, plus a 100-row CSV batch timing.
"""
from __future__ import annotations
import argparse, csv, json, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

QA = Path(__file__).resolve().parent
ERR = {"mismatch", "out_of_range", "unit", "not_allowed", "new_property"}


def post(base, body, raw=None):
    data = raw if raw is not None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base + "/api/analyze", data=data, headers={"Content-Type": "application/json"})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r), (time.perf_counter() - t) * 1000
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except Exception:
            d = None
        return e.code, d, (time.perf_counter() - t) * 1000


def best(d):
    return ((d or {}).get("best_ktru") or {}).get("code", "") or ""


def has_err_issue(d, sev=None):
    return any(i["type"] in ERR and (sev is None or i["severity"] == sev) for i in (d or {}).get("issues", []))


def check(c, s, d, ms, ctx):
    st = (d or {}).get("status")
    g, i = c["group"], c["id"]
    if s >= 500:
        return False, "HTTP 500"
    if g == "absurd":
        return s == 200 and has_err_issue(d), f"issues={[x['type'] for x in d['issues']]}"
    if g in ("garbage", "out_of_scope") or i == "B06" or i == "B22":
        return s == 200 and st == "not_found", f"status={st} best={best(d)}"
    if i == "B05":
        return s == 200 and best(d).startswith("31."), f"best={best(d)}"
    if g == "long":
        return s in (200, 413, 422) and ms < 5000, f"len={len(c['query'])} ms={ms:.0f}"
    if i == "B12":
        return s == 422, f"http={s} detail={str((d or {}).get('detail'))[:80]}"
    if g == "empty":
        return s == 422 or st == "not_found", f"http={s} status={st}"
    if g == "synonym":
        names = sorted(x["name"] for x in d["characteristics"] if x.get("user_input"))
        ctx[i] = (best(d), names)
        if i == "B16":
            a, b = ctx["B15"], ctx["B16"]
            return a == b, f"B15={a} B16={b}"
        return True, f"best={best(d)} chars={names}"
    if g == "incomplete":
        return s == 200 and best(d).startswith("31.01") and st in ("need_more", "ok", "ambiguous"), f"status={st} best={best(d)} next={d.get('next_steps')}"
    if g.startswith("fake_code"):
        return s == 200 and not best(d).startswith(("99.", "31.01.10.000-00000099")), f"status={st} best={best(d)}"
    if g == "sql":
        s2, d2, _ = post(ctx["base"], {"text": "Стол письменный ЛДСП"})
        return s == 200 and s2 == 200 and best(d2).startswith("31."), f"status={st}; follow-up best={best(d2)}"
    if g == "html":
        return s == 200, f"status={st} best={best(d)}"
    if g in ("bad_domain", "null_text", "not_json"):
        return s == 422, f"http={s}"
    if g in ("huge_number", "negative", "zero"):
        return s == 200 and has_err_issue(d, "error"), f"status={st} issues={[(x['type'], x['severity']) for x in d['issues']]}"
    if g == "translit":
        return s == 200 and st != "not_found", f"status={st} best={best(d)}"
    return s == 200, f"status={st}"


def main():
    a = argparse.ArgumentParser(); a.add_argument("--base", default="http://127.0.0.1:8814"); base = a.parse_args().base
    ctx, rows = {"base": base}, []
    for c in csv.DictReader((QA / "break.csv").open(encoding="utf-8-sig")):
        body = {"text": c["query"]}
        if c["domain_hint"]:
            body["domain_hint"] = c["domain_hint"]
        raw = None
        if c["group"] == "fake_code_field":
            body["characteristics"] = [{"name": "Код КТРУ", "value": "99.99.99.999-00000001", "unit": None}]
        if c["group"] == "null_text":
            body["text"] = None
        if c["group"] == "not_json":
            raw = b"text=hello"
        s, d, ms = post(base, body, raw)
        ok, info = check(c, s, d, ms, ctx)
        rows.append({"id": c["id"], "group": c["group"], "http": s, "ms": round(ms), "result": "PASS" if ok else "FAIL", "info": info[:300]})
        print(rows[-1]["id"], rows[-1]["group"], s, f"{ms:.0f}ms", rows[-1]["result"], "|", info[:200])
    with (QA / "break_results.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print("PASS", sum(r["result"] == "PASS" for r in rows), "из", len(rows))
    # batch: no CSV/batch endpoint in the app -> 100 rows (45 dev + 45 holdout + 10 broken) sent one by one through /api/analyze
    q = [r["query"] for r in csv.DictReader((QA / "cases.csv").open(encoding="utf-8-sig"))]
    q += [r["query"] for r in csv.DictReader((QA / "holdout.csv").open(encoding="utf-8-sig"))]
    q += ["", "   ", "asdkjh", "😀😀", "Хлеб 500 г", "' OR 1=1 --", "<b>x</b>", "Стол высота -1 мм", "Ключ мощность 100", "Молоток масса 900 кг"]
    for workers in (1, 4):
        t = time.perf_counter()
        with ThreadPoolExecutor(workers) as ex:
            res = list(ex.map(lambda x: post(base, {"text": x})[0], q))
        dt = time.perf_counter() - t
        print(f"batch {len(q)} rows, {workers} parallel: {dt:.1f} s; http codes {sorted(set(res))}; 500s={res.count(500)}")


if __name__ == "__main__":
    main()
