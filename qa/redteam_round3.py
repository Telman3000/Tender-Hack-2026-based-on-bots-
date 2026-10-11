"""Round-3 red-team: portal index, CSV edge cases, homoglyphs, units, concurrency."""
from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "http://127.0.0.1:8000"


def analyze(body: dict) -> tuple[int, dict | None, float]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/analyze", data=data, headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r), (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except Exception:
            d = {"detail": e.read().decode("utf-8", errors="replace")[:500]}
        return e.code, d, (time.perf_counter() - t0) * 1000


def csv_upload(raw: bytes, filename: str = "t.csv") -> tuple[int, dict | None, float]:
    boundary = "----redteam3"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8") + raw + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/analyze/csv",
        body,
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.load(r), (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except Exception:
            d = {"detail": e.read()[:500].decode("utf-8", errors="replace")}
        return e.code, d, (time.perf_counter() - t0) * 1000


def summarize(label: str, code: int, d: dict | None, ms: float) -> None:
    if d is None:
        print(f"{label}\tHTTP {code}\t{ms:.0f}ms")
        return
    if "detail" in d and "status" not in d:
        print(f"{label}\tHTTP {code}\t{ms:.0f}ms\tdetail={str(d['detail'])[:120]}")
        return
    bk = d.get("best_ktru") or {}
    chars = d.get("characteristics") or []
    src = {c.get("source") for c in chars}
    issues = [f"{i.get('type')}:{i.get('severity')}" for i in d.get("issues") or []]
    print(
        f"{label}\t{d.get('status')}\t{d.get('card_status')}\t"
        f"{bk.get('code', '—')}\tchars={len(chars)} src={src}\tissues={issues[:4]}\t{ms:.0f}ms"
    )


def main() -> None:
    probes: list[tuple[str, dict]] = [
        ("cl01_official", {
            "text": "Костюм рабочий мужской размер 48-50 рост 170-176",
            "domain_hint": "clothing",
        }),
        ("homoglyph_latin_o", {
            "text": "St\u043el pismennyi LDSP vysota 750 mm",  # St + Cyrillic о
            "domain_hint": "furniture",
        }),
        ("mixed_cyr_lat", {"text": "Стол pismennyi ЛДСП 750 мм", "domain_hint": "furniture"}),
        ("instruments_violin", {"text": "Скрипка учебная 4/4", "domain_hint": "tools"}),
        ("instruments_piano", {"text": "Пианино акустическое", "domain_hint": "furniture"}),
        ("range_dash_en", {"text": "Костюм рабочий размер 48-50 рост 170–176", "domain_hint": "clothing"}),
        ("range_slash", {"text": "Костюм рабочий размер 48/50", "domain_hint": "clothing"}),
        ("version_explicit_old", {
            "text": "Стол письменный код 31.01.10.000-00000004",
            "domain_hint": "furniture",
        }),
        ("version_explicit_new", {
            "text": "Стол письменный код 31.01.10.000-00000006",
            "domain_hint": "furniture",
        }),
        ("h17_filler", {
            "text": "Костюм рабочий наполнитель высокоэластичный поролон размер 50",
            "domain_hint": "clothing",
        }),
        ("unit_micron", {"text": "Стол письменный толщина столешницы 16 мкм", "domain_hint": "furniture"}),
        ("unit_ton_joke", {"text": "Молоток слесарный масса 0.5 т", "domain_hint": "tools"}),
        ("negative_size", {"text": "Стол письменный ширина -1200 мм", "domain_hint": "furniture"}),
        ("zero_height", {"text": "Стол письменный высота 0 мм", "domain_hint": "furniture"}),
        ("duplicate_mass_portal", {
            "text": "Молоток слесарный",
            "domain_hint": "tools",
            "characteristics": [
                {"name": "Масса молотка", "value": "500", "unit": "г"},
                {"name": "Масса молotka", "value": "900", "unit": "г"},
            ],
        }),
    ]
    for label, body in probes:
        code, d, ms = analyze(body)
        summarize(label, code, d, ms)

    csv_cases: list[tuple[str, bytes]] = [
        ("utf8_bom", "\ufeffname\nСтол письменный\n".encode("utf-8")),
        ("semicolon_cp1251", "name;товар\nСтол; письменный\n".encode("cp1251")),
        ("tab_delim", "name\ttext\n\tСтол письменный\n".encode("utf-8")),
        ("quoted_comma", 'name\n"Стол, письменный"\n'.encode("utf-8")),
        ("empty_rows", "name\n\n\nСтол письменный\n".encode("utf-8")),
        ("duplicate_id_batch", None),  # handled below
        ("latin1_header", b"name\nM\xf6bel\n"),
    ]
    for label, raw in csv_cases:
        if raw is None:
            continue
        code, d, ms = csv_upload(raw)
        if code == 200 and d:
            rows = d.get("rows") or d.get("results") or []
            n = len(rows) if isinstance(rows, list) else "?"
            print(f"csv_{label}\t200\trows={n}\t{ms:.0f}ms")
            if isinstance(rows, list) and rows:
                r0 = rows[0]
                inner = r0.get("result") or r0
                bk = (inner.get("best_ktru") or {}) if isinstance(inner, dict) else {}
                print(f"  first: {inner.get('status') if isinstance(inner, dict) else r0} {bk.get('code')}")
        else:
            summarize(f"csv_{label}", code, d, ms)

    # NDJSON batch duplicate ids
    batch = {"items": [{"id": "dup", "text": "Стол письменный", "domain_hint": "furniture"},
                       {"id": "dup", "text": "Молоток слесарный", "domain_hint": "tools"}]}
    data = json.dumps(batch, ensure_ascii=False).encode()
    req = urllib.request.Request(
        BASE + "/api/analyze/batch",
        data,
        {"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.load(r)
            ms = (time.perf_counter() - t0) * 1000
            items = d.get("items") or []
            codes = []
            for it in items:
                inner = it.get("result") or it
                bk = (inner.get("best_ktru") or {}) if isinstance(inner, dict) else {}
                codes.append(bk.get("code"))
            print(f"batch_dup_id\t200\tcodes={codes}\t{ms:.0f}ms")
    except urllib.error.HTTPError as e:
        print(f"batch_dup_id\t{e.code}\t{(time.perf_counter()-t0)*1000:.0f}ms")

    # concurrency same text different hints
    text = "Стол письменный ЛДСП высота 750 мм"
    hints = ["furniture", "tools", "clothing", None]
    def one(h):
        b = {"text": text}
        if h:
            b["domain_hint"] = h
        _, d, ms = analyze(b)
        bk = (d or {}).get("best_ktru") or {}
        return h, bk.get("code"), ms

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(one, h) for h in hints * 5]
        codes = {}
        for f in as_completed(futs):
            h, c, ms = f.result()
            codes.setdefault(h, set()).add(c)
        print(f"concurrent_hints\t{ {k: list(v) for k, v in codes.items()} }")


if __name__ == "__main__":
    main()
