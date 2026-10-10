"""Error detection and false alarms.
python qa/run_holdout.py  -> qa/errors_results.csv, qa/false_alarms.csv, prints N из M.
Detection: an issue whose type is in the case's expected_issue_types, or status 'error' for unit/unrealistic/nonexistent.
False alarm on clean cases (cases.csv clean + holdout.csv clean):
  strict = status 'error' or any issue with severity 'error';
  soft   = any warning other than missing/ambiguous (typo, unit, mismatch, not_allowed, new_property, ...).
"""
from __future__ import annotations
import csv, sys
from collections import defaultdict
from pathlib import Path

QA = Path(__file__).resolve().parent
sys.path.insert(0, str(QA.parent))
from app.engine import CatalogEngine  # noqa: E402
from app.models import AnalyzeRequest  # noqa: E402


def issues(r):
    return [(getattr(i, "type", "") or getattr(i, "kind", ""), getattr(i, "severity", ""), i.message) for i in r.issues]


def main():
    eng = CatalogEngine()
    rows, by = [], defaultdict(lambda: [0, 0])
    for c in csv.DictReader((QA / "errors.csv").open(encoding="utf-8-sig")):
        r = eng.analyze(AnalyzeRequest(text=c["query"], domain_hint=c["category"]))
        iss = issues(r); exp = set(c["expected_issue_types"].split("|"))
        hit = any(t in exp for t, _, _ in iss) or (c["error_type"] != "typo" and r.status == "error")
        by[c["error_type"]][0] += hit; by[c["error_type"]][1] += 1
        rows.append({**c, "status": r.status, "detected": int(hit), "issues": " ; ".join(f"{t}/{s}: {m}" for t, s, m in iss)[:400]})
    with (QA / "errors_results.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    fa = []
    for fn in ("cases.csv", "holdout.csv"):
        for c in csv.DictReader((QA / fn).open(encoding="utf-8-sig")):
            if c["type"] != "clean":
                continue
            r = eng.analyze(AnalyzeRequest(text=c["query"], domain_hint=c["category"]))
            iss = issues(r)
            strict = r.status == "error" or any(s == "error" for _, s, _ in iss)
            soft = [f"{t}: {m}" for t, s, m in iss if s != "error" and t not in ("missing", "ambiguous")]
            fa.append({"set": fn, "id": c["id"], "query": c["query"], "status": r.status, "strict": int(strict),
                       "soft": int(bool(soft)), "flags": " ; ".join([f"{t}/{s}: {m}" for t, s, m in iss if s == "error"] + soft)[:400]})
    eng.close()
    with (QA / "false_alarms.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(fa[0])); w.writeheader(); w.writerows(fa)
    tot = sum(v[0] for v in by.values()), sum(v[1] for v in by.values())
    print(f"detection: {tot[0]} из {tot[1]}")
    for k, (h, n) in sorted(by.items()):
        print(f"  {k}: {h} из {n}")
    print(f"false alarms strict: {sum(x['strict'] for x in fa)} из {len(fa)}; soft: {sum(x['soft'] for x in fa)} из {len(fa)}")
    for x in fa:
        if x["strict"] or x["soft"]:
            print("  FA", x["set"], x["id"], x["status"], "|", x["query"][:80], "|", x["flags"][:200])
    for x in rows:
        if not x["detected"]:
            print("  MISS", x["id"], x["error_type"], x["status"], "|", x["query"], "|", x["issues"][:200])


if __name__ == "__main__":
    main()
