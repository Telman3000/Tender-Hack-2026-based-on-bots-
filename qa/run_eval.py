"""QA eval: python qa/run_eval.py  (from repo root). Writes qa/results.csv, qa/summary.md."""
from __future__ import annotations
import csv, statistics, subprocess, sys, time
from collections import defaultdict
from pathlib import Path

QA = Path(__file__).resolve().parent
ROOT = QA.parent
sys.path.insert(0, str(ROOT))
from app.engine import CatalogEngine  # noqa: E402
from app.models import AnalyzeRequest  # noqa: E402


def match(code, exp):
    return bool(code) and any(code.startswith(e) for e in exp.split("|"))


def status_ok(c, st, top):
    """Status must be allowed for the case AND consistent with the code:
    clean+ok needs a correct top-1; clean+ambiguous/need_more needs the group in top-3."""
    exp = c["expected_code"]
    if st not in c["expected_status"].split("|"):
        return 0
    if c["type"] == "clean":
        if st == "ok":
            return int(match(top[0] if top else "", exp))
        return int(any(match(x, exp) for x in top[:3]))
    return 1


def group(exp):  # KTRU group = first two OKPD2 levels, e.g. 31.01
    return "|".join(".".join(e.split(".")[:2]) for e in exp.split("|"))


def pct(xs):
    return f"{100*sum(xs)/len(xs):.0f}%" if xs else "-"


def main(hint=True, suffix="", cases_file="cases.csv"):
    cases = list(csv.DictReader((QA / cases_file).open(encoding="utf-8-sig")))
    eng = CatalogEngine()
    eng.analyze(AnalyzeRequest(text="стол"))  # warmup
    rows = []
    for c in cases:
        t = time.perf_counter()
        try:
            r = eng.analyze(AnalyzeRequest(text=c["query"], domain_hint=c["category"] if hint else None))
            err = ""
        except Exception as e:  # noqa: BLE001
            r, err = None, repr(e)
        ms = (time.perf_counter() - t) * 1000
        top = []
        if r:
            if r.best_ktru: top.append(r.best_ktru.code)
            for s in reversed(r.narrowing):
                top += [x.code for x in s.top]
            top = list(dict.fromkeys(top))
        exp = c["expected_code"]
        st = r.status if r else "exception"
        rows.append({**c, "status": st, "domain": r.detected_domain if r else "",
            "product": r.product_guess if r else "", "best": top[0] if top else "",
            "top3": " ".join(top[:3]),
            "top1_ok": int(match(top[0] if top else "", exp)),
            "top3_ok": int(any(match(x, exp) for x in top[:3])),
            "group_ok": int(any(match(x, group(exp)) for x in top[:3])),
            "status_ok": status_ok(c, st, top),
            "confident_wrong": int(st == "ok" and not match(top[0] if top else "", exp)),
            "false_confident": int(c["type"] == "error" and st == "ok"),
            "n_chars": len(r.characteristics) if r else 0,
            "issues": "; ".join(f"{i.kind}:{i.message}" for i in r.issues)[:300] if r else err,
            "latency_ms": round(ms, 1)})
    eng.close()
    with (QA / f"results{suffix}.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    def block(rs):
        lat = sorted(r["latency_ms"] for r in rs)
        err = [r["false_confident"] for r in rs if r["type"] == "error"]
        p95 = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
        return [str(len(rs)), pct([r["top1_ok"] for r in rs]), pct([r["top3_ok"] for r in rs]),
                pct([r["group_ok"] for r in rs]), pct([r["status_ok"] for r in rs]), pct(err), pct([r["confident_wrong"] for r in rs]),
                f"{statistics.median(lat):.0f}", f"{p95:.0f}", f"{lat[-1]:.0f}"]
    hdr = "| slice | n | top-1 | top-3 | group | status | false-confident (err) | ok-but-wrong-code | p50 ms | p95 ms | max ms |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
    lines = [f"| ALL | " + " | ".join(block(rows)) + " |"]
    for key in ("category", "type"):
        g = defaultdict(list)
        for r in rows: g[r[key]].append(r)
        lines += [f"| {key}={k} | " + " | ".join(block(v)) + " |" for k, v in sorted(g.items())]
    try:
        rev = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
        br = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        rev = br = "?"
    fails = [r for r in rows if not (r["top3_ok"] and r["status_ok"])]
    md = [f"# QA eval — {br}@{rev}, {time.strftime('%Y-%m-%d %H:%M')}", "",
          f"Cases: {len(rows)}; domain_hint={'on' if hint else 'off'}. Status accepted sets per case are in cases.csv "
          "(clean: ok counts only with correct top-1; ambiguous/need_more only if expected group is in top-3; incomplete: need_more|ambiguous; error: anything except ok).", "",
          hdr + "\n".join(lines), "", "## Failures (top-3 miss or wrong status)", "",
          "| id | type | query | expected | got top3 | status | domain |", "|---|---|---|---|---|---|---|"]
    md += [f"| {r['id']} | {r['type']} | {r['query']} | {r['expected_code']} / {r['expected_status']} | {r['top3']} | {r['status']} | {r['domain']} |" for r in fails]
    (QA / f"summary{suffix}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    sfx = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--suffix=")), "")
    cf = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--cases=")), "cases.csv")
    main(hint="--no-hint" not in sys.argv, suffix=sfx, cases_file=cf)


