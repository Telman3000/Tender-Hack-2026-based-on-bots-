"""QA eval: python qa/run_eval.py  (from repo root). Writes qa/results.csv, qa/summary.md.

Shortlist completeness is printed as k/n. A percentage without the fraction is not a result.
The run does not call a language model.
"""
from __future__ import annotations
import csv, statistics, subprocess, sys, time
from collections import defaultdict
from pathlib import Path

QA = Path(__file__).resolve().parent
ROOT = QA.parent
sys.path.insert(0, str(ROOT))
from app.db import db_ready  # noqa: E402
from app.engine import CatalogEngine  # noqa: E402
from app.models import AnalyzeRequest  # noqa: E402

MODEL_LINE = "Основной путь — текущий разбор без модели."

# Kept so a regeneration does not drop the measured baseline from main.
_BASELINE = """\
Базовый прогон 45 кейсов на main (каталог собран, 2026-10-10): top-1 44/45, top-3 45/45.
По категориям: clothing 14/15, furniture 15/15, tools 15/15. Ложной уверенности 0/15.
UI: smoke и ui_accept проходили на том прогоне (FU19, TO37, TO42).
"""


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


def kn(xs) -> str:
    n = len(xs)
    if not n:
        return "0/0"
    return f"{sum(xs)}/{n}"


def pct_kn(xs) -> str:
    """Fraction first. A bare percentage is not used."""
    if not xs:
        return "0/0"
    return f"{kn(xs)} ({100 * sum(xs) / len(xs):.0f}%)"


def pre_final_codes(response) -> list[str]:
    """Codes visible before the final narrowing step.

    When person 1 adds `search.shortlist` (or `search.codes`), that full list is used.
    Until then the metric reads every code the API already returns on steps other than
    «Итог», plus codes removed on the final step (they were inside the pre-final set).
    """
    if response is None:
        return []
    search = getattr(response, "search", None)
    debug = getattr(response, "debug", None)
    if search is None and isinstance(debug, dict):
        search = debug.get("search")
    if isinstance(search, dict):
        raw = search.get("shortlist") or search.get("codes") or search.get("candidates") or []
        codes: list[str] = []
        for item in raw:
            if isinstance(item, str):
                codes.append(item)
            elif isinstance(item, dict) and item.get("code"):
                codes.append(str(item["code"]))
        if codes:
            return list(dict.fromkeys(codes))
    codes = []
    for step in getattr(response, "narrowing", None) or []:
        label = getattr(step, "label", "") or ""
        stage = getattr(step, "stage", "") or ""
        final = label == "Итог" or stage in {"final", "ambiguous"}
        if not final:
            codes.extend(x.code for x in (getattr(step, "top", None) or []))
            codes.extend(getattr(step, "removed_codes", None) or [])
        else:
            codes.extend(getattr(step, "removed_codes", None) or [])
            codes.extend(x.code for x in (getattr(step, "top", None) or []))
    best = getattr(response, "best_ktru", None)
    if best is not None and getattr(best, "code", None):
        codes.append(best.code)
    return list(dict.fromkeys(codes))


def shortlist_hit(response, expected_code: str) -> int:
    wanted = group(expected_code)
    return int(any(match(code, wanted) for code in pre_final_codes(response)))


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _eval_rows(eng: CatalogEngine, cases: list[dict], hint: bool) -> list[dict]:
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
            if r.best_ktru:
                top.append(r.best_ktru.code)
            for s in reversed(r.narrowing):
                top += [x.code for x in s.top]
            top = list(dict.fromkeys(top))
        exp = c["expected_code"]
        st = r.status if r else "exception"
        rows.append({
            **c,
            "status": st,
            "domain": r.detected_domain if r else "",
            "product": r.product_guess if r else "",
            "best": top[0] if top else "",
            "top3": " ".join(top[:3]),
            "top1_ok": int(match(top[0] if top else "", exp)),
            "top3_ok": int(any(match(x, exp) for x in top[:3])),
            "group_ok": int(any(match(x, group(exp)) for x in top[:3])),
            "shortlist_ok": shortlist_hit(r, exp) if r else 0,
            "status_ok": status_ok(c, st, top),
            "confident_wrong": int(st == "ok" and not match(top[0] if top else "", exp)),
            "false_confident": int(c["type"] == "error" and st == "ok"),
            "n_chars": len(r.characteristics) if r else 0,
            "issues": "; ".join(f"{i.kind}:{i.message}" for i in r.issues)[:300] if r else err,
            "latency_ms": round(ms, 1),
        })
    return rows


def _same_codes(a: list[dict], b: list[dict]) -> int:
    n = 0
    for left, right in zip(a, b):
        if left["best"] == right["best"] and left["status"] == right["status"]:
            n += 1
    return n


def _block(rs: list[dict]) -> list[str]:
    lat = sorted(r["latency_ms"] for r in rs)
    err = [r["false_confident"] for r in rs if r["type"] == "error"]
    p95 = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))] if lat else 0
    return [
        str(len(rs)),
        pct_kn([r["top1_ok"] for r in rs]),
        pct_kn([r["top3_ok"] for r in rs]),
        pct_kn([r["group_ok"] for r in rs]),
        pct_kn([r["status_ok"] for r in rs]),
        pct_kn(err) if err else "0/0",
        pct_kn([r["confident_wrong"] for r in rs]),
        f"{statistics.median(lat):.0f}" if lat else "0",
        f"{p95:.0f}",
        f"{lat[-1]:.0f}" if lat else "0",
    ]


def _slices(rows: list[dict]) -> list[str]:
    hdr = (
        "| slice | n | top-1 | top-3 | group | status | false-confident (err) | "
        "ok-but-wrong-code | p50 ms | p95 ms | max ms |"
    )
    sep = "|---|---|---|---|---|---|---|---|---|---|---|"
    lines = [hdr, sep, "| ALL | " + " | ".join(_block(rows)) + " |"]
    keys = ["category", "type"]
    if any(r.get("set") for r in rows):
        keys.append("set")
    for key in keys:
        grouped: dict[str, list] = defaultdict(list)
        for r in rows:
            grouped[r.get(key) or ""].append(r)
        for name in sorted(grouped):
            if not name:
                continue
            lines.append(f"| {key}={name} | " + " | ".join(_block(grouped[name])) + " |")
    return lines


def _shortlist_table(rows: list[dict], measured: bool) -> list[str]:
    lines = [
        "| slice | полнота короткого списка |",
        "|---|---|",
    ]
    if not measured:
        lines.append("| ALL | 0/0 |")
        lines.append("| category=clothing | 0/0 |")
        lines.append("| category=furniture | 0/0 |")
        lines.append("| category=tools | 0/0 |")
        lines.append("")
        lines.append("Каталог catalog.db не загружен: полнота короткого списка не измерена.")
        return lines

    def cell(rs: list[dict]) -> str:
        return kn([r["shortlist_ok"] for r in rs])

    lines.append(f"| ALL | {cell(rows)} |")
    grouped: dict[str, list] = defaultdict(list)
    for r in rows:
        grouped[r.get("category") or ""].append(r)
    for name in ("clothing", "furniture", "tools"):
        lines.append(f"| category={name} | {cell(grouped.get(name, []))} |")
    return lines


def _failures(rows: list[dict]) -> list[str]:
    fails = [r for r in rows if not (r["top3_ok"] and r["status_ok"])]
    lines = [
        "| id | type | query | expected | got top3 | status | domain |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['id']} | {r['type']} | {r['query']} | {r['expected_code']} / {r['expected_status']} | {r['top3']} | {r['status']} | {r['domain']} |"
        for r in fails
    ]
    return lines


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main(hint=True, suffix=""):
    cases = _load(QA / "cases.csv")
    perturb = _load(QA / "cases_perturb.csv")
    measured = db_ready()
    eng = CatalogEngine()
    if cases:
        eng.analyze(AnalyzeRequest(text="стол"))  # warmup
    first = _eval_rows(eng, cases, hint)
    second = _eval_rows(eng, cases, hint)
    perturb_rows = _eval_rows(eng, perturb, hint)
    perturb_again = _eval_rows(eng, perturb, hint)
    eng.close()

    # Without the built catalog every code is empty. Do not replace the measured
    # results.csv / summary.md from main with that empty run.
    persist = measured or suffix != ""
    if not persist:
        print("catalog.db нет: отчёт ниже напечатан, qa/results.csv и qa/summary.md не перезаписаны.")
        print("Соберите индекс и запустите команду снова, чтобы записать k/n.")

    try:
        rev = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
        br = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        rev = br = "?"

    same = _same_codes(first, second)
    same_p = _same_codes(perturb_rows, perturb_again)
    md = [
        f"# QA eval — {br}@{rev}, {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        MODEL_LINE,
        "",
        f"Cases: {len(first)}; domain_hint={'on' if hint else 'off'}. "
        "Числа качества записаны как k/n. Полнота короткого списка — только k/n, без отдельного процента.",
        "clean+ok считается верным только при верном top-1; clean+ambiguous/need_more — если ожидаемая группа есть в top-3.",
        "",
    ]
    md.extend(_slices(first) if first else ["Нет строк в cases.csv."])
    md.extend([
        "",
        "## Полнота короткого списка",
        "",
        "Доля кейсов, где ожидаемая группа есть среди кодов до финального отсечения.",
        "",
    ])
    md.extend(_shortlist_table(first, measured))
    md.extend([
        "",
        f"Повторный прогон cases.csv: коды и статусы совпали, {same}/{len(first) if first else 0}.",
        "",
        "## Искажения (qa/cases_perturb.csv)",
        "",
    ])
    md.extend(_slices(perturb_rows) if perturb_rows else ["Файл искажений пуст."])
    md.append("")
    if perturb_rows:
        md.extend(_shortlist_table(perturb_rows, measured))
        md.append("")
    md.extend([
        f"Повторный прогон искажений: коды и статусы совпали, {same_p}/{len(perturb_rows) if perturb_rows else 0}.",
        "",
        "## Failures (top-3 miss or wrong status)",
        "",
    ])
    md.extend(_failures(first))
    md.extend(["", "## Базовый прогон", "", _BASELINE.strip(), ""])
    if persist:
        _write_csv(QA / f"results{suffix}.csv", first)
        _write_csv(QA / f"results_perturb{suffix}.csv", perturb_rows)
        (QA / f"summary{suffix}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    if first:
        print("\n".join(_slices(first)))
        print("\n".join(_shortlist_table(first, measured)))
    print(MODEL_LINE)
    print(f"deterministic {same}/{len(first) if first else 0}")


if __name__ == "__main__":
    sfx = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--suffix=")), "")
    main(hint="--no-hint" not in sys.argv, suffix=sfx)
