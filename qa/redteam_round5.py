"""Round-5 probes: symbols, injection, batch/csv duplicates, portal STE hints."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def post(path: str, body: bytes, headers: dict) -> dict | str:
    req = urllib.request.Request(BASE + path, body, headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            ct = r.headers.get("Content-Type", "")
            raw = r.read()
            if "json" in ct:
                return json.loads(raw)
            return raw.decode("utf-8", errors="replace")[:500]
    except urllib.error.HTTPError as e:
        return {"http": e.code, "body": e.read()[:300].decode("utf-8", errors="replace")}


def analyze(body: dict) -> dict:
    return post("/api/analyze", json.dumps(body, ensure_ascii=False).encode(), {"Content-Type": "application/json"})  # type: ignore


def main() -> None:
    tests = [
        ("diameter_o", {"text": "Труба стальная диаметр Ø15 мм", "domain_hint": "tools"}),
        ("times_sign", {"text": "Стол письменный 1200×750 мм", "domain_hint": "furniture"}),
        ("ru_m_x", {"text": "Стол письменный 1200х750 мм", "domain_hint": "furniture"}),
        ("null_in_text", {"text": "Стол письменный\u0000 скрытый", "domain_hint": "furniture"}),
        ("rtl_override", {"text": "Стол письменный \u202e750 мм", "domain_hint": "furniture"}),
        ("double_space", {"text": "Стол  письменный   ЛДСП", "domain_hint": "furniture"}),
        ("ktu_code_typo", {"text": "Стол письменный КТРУ 31.O1.10.000-00000004", "domain_hint": "furniture"}),
        ("ste_id_in_text", {"text": "Стол письменный ste_id=12345678", "domain_hint": "furniture"}),
        ("html_tag", {"text": "Стол письменный <b>ЛДСП</b> 750мм", "domain_hint": "furniture"}),
        ("sql_frag", {"text": "Стол'; DROP TABLE ktru;--", "domain_hint": "furniture"}),
    ]
    for label, body in tests:
        d = analyze(body)
        if not isinstance(d, dict) or "status" not in d:
            print(label, "WEIRD", d)
            continue
        bk = d.get("best_ktru") or {}
        print(
            f"{label}\t{d['status']}\t{bk.get('code','—')}\t"
            f"issues={[i['type'] for i in d.get('issues',[])][:4]}"
        )

    # batch: 3 same id
    batch = {
        "items": [
            {"id": "x", "text": "Стол письменный", "domain_hint": "furniture"},
            {"id": "x", "text": "Молоток слесарный", "domain_hint": "tools"},
            {"id": "x", "text": "Костюм рабочий", "domain_hint": "clothing"},
        ]
    }
    d = post("/api/analyze/batch", json.dumps(batch, ensure_ascii=False).encode(), {"Content-Type": "application/json"})
    if isinstance(d, dict):
        codes = []
        for r in d.get("results", []):
            bk = (r.get("best_ktru") or {})
            codes.append(bk.get("code"))
        print("batch_triple_id", codes)

    # csv 1000 rows timing
    import time

    rows = "name\n" + "\n".join(["Стол письменный"] * 1000) + "\n"
    b = "----5"
    raw = rows.encode("utf-8")
    body = (
        f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"big.csv\"\r\n"
        f"Content-Type: text/csv\r\n\r\n"
    ).encode() + raw + f"\r\n--{b}--\r\n".encode()
    t0 = time.perf_counter()
    d = post("/api/analyze/csv", body, {"Content-Type": f"multipart/form-data; boundary={b}"})
    print("csv_1000", "summary" in str(d), f"{(time.perf_counter()-t0)*1000:.0f}ms", d.get("summary") if isinstance(d, dict) else d)


if __name__ == "__main__":
    main()
