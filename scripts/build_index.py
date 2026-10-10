"""Build SQLite catalog from hackathon materials (КТРУ XML + Excel выгрузки)."""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree
from openpyxl import load_workbook

# Windows consoles often use cp1251 — keep logs ASCII-safe
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DOMAIN_KEYWORDS, OKPD2_PREFIXES  # noqa: E402
from app.db import connect, ensure_processed_dir, init_schema, set_meta  # noqa: E402
from app.config import DB_PATH  # noqa: E402


NS = {
    "oos": "http://zakupki.gov.ru/oos/types/1",
    "ex": "http://zakupki.gov.ru/oos/export/1",
}


def _norm(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[^a-zа-я0-9\s\-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def detect_domain_from_text(text: str, okpd2: str | None = None) -> str | None:
    if okpd2:
        for domain, prefixes in OKPD2_PREFIXES.items():
            if any(okpd2.startswith(p) for p in prefixes):
                return domain
        # OKPD2 is authoritative: out-of-scope group means out of scope
        return None
    low = (text or "").lower()
    scores = {
        d: sum(1 for kw in kws if kw in low) for d, kws in DOMAIN_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def find_materials_root(path: Path) -> Path:
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    # If zip — extract lightly to _materials
    if path.is_file() and path.suffix.lower() == ".zip":
        out = ROOT / "_materials"
        out.mkdir(exist_ok=True)
        with zipfile.ZipFile(path) as z:
            z.extractall(out)
        path = out
    # Find folder containing xlsx or ktru zip
    xlsx = list(path.rglob("*.xlsx"))
    if xlsx:
        return xlsx[0].parents[1] if len(xlsx[0].parts) > 1 else path
    return path


def find_ktru_outer_zip(materials: Path) -> Path | None:
    zips = list(materials.rglob("*.zip"))
    # Prefer the big one (~100MB)
    zips = sorted(zips, key=lambda p: -p.stat().st_size)
    return zips[0] if zips else None


def find_excel_files(materials: Path) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for p in materials.rglob("*.xlsx"):
        name = p.name.lower()
        # Cyrillic filenames may be mojibake; use size heuristics + content later
        mapping[p.name] = p
    # Classify by reading first STE name keywords
    classified: dict[str, Path] = {}
    for name, p in mapping.items():
        try:
            wb = load_workbook(p, read_only=True, data_only=True)
            ws = wb[wb.sheetnames[0]]
            sample_names = []
            for i, row in enumerate(ws.iter_rows(min_row=2, max_row=30, values_only=True)):
                if row and row[1]:
                    sample_names.append(str(row[1]))
            wb.close()
            blob = " ".join(sample_names).lower()
            domain = detect_domain_from_text(blob)
            if domain and domain not in classified:
                classified[domain] = p
                print(f"  Excel {p.name} -> domain={domain}")
        except Exception as e:
            print(f"  skip excel {p}: {e}")
    return classified


def ingest_portal_excel(conn, domain: str, path: Path, ste_limit: int = 25000) -> None:
    print(f"[portal] {domain}: {path.name}")
    wb = load_workbook(path, read_only=True, data_only=True)

    # Sheet1 — STE
    ws1 = wb[wb.sheetnames[0]]
    n = 0
    for row in ws1.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        ste_id = str(row[0])
        name = str(row[1] or "")
        manufacturer = str(row[3] or "") if len(row) > 3 else ""
        chars_raw = str(row[5] or "") if len(row) > 5 else ""
        conn.execute(
            """
            INSERT INTO portal_ste(ste_id, name, domain, manufacturer, chars_raw, name_norm)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(ste_id) DO UPDATE SET
              name=excluded.name, domain=excluded.domain, chars_raw=excluded.chars_raw,
              name_norm=excluded.name_norm
            """,
            (ste_id, name, domain, manufacturer, chars_raw, _norm(name)),
        )
        n += 1
        if n >= ste_limit:
            break
        if n % 5000 == 0:
            conn.commit()
            print(f"    STE rows: {n}")
    conn.commit()
    print(f"    STE total: {n}")

    # Sheet2 — characteristic schema
    if len(wb.sheetnames) > 1:
        ws2 = wb[wb.sheetnames[1]]
        c = 0
        for row in ws2.iter_rows(min_row=2, values_only=True):
            if not row or not row[3]:
                continue
            category = str(row[0] or "")
            # skip garbage categories
            if "не найдено значение" in category.lower() or len(category) > 120:
                continue
            kpgz = str(row[1] or "")
            char_name = str(row[3] or "").strip()
            char_type = str(row[4] or "")
            unit = str(row[7] or "") if len(row) > 7 and row[7] else None
            values_sample = str(row[6] or "")[:500] if len(row) > 6 and row[6] else None
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO portal_chars
                    (domain, category, kpgz_code, char_name, char_type, unit, values_sample)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (domain, category, kpgz, char_name, char_type, unit, values_sample),
                )
                c += 1
            except Exception:
                pass
            if c % 10000 == 0 and c:
                conn.commit()
        conn.commit()
        print(f"    portal_chars: {c}")
    wb.close()


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


SKIP_STATUSES = {"INACTIVE", "TERMINATED", "EXCLUDED", "DELETED", "CANCELLED"}


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def _parse_characteristic(ch) -> dict | None:
    """Characteristic with its allowed values: qualitative list, concrete numbers, ranges + OKEI."""
    name = None
    required = False
    values: list[dict] = []
    for sub in ch:
        sl = _local(sub.tag)
        if sl == "name":
            name = (sub.text or "").strip()
        elif sl == "isRequired":
            required = (sub.text or "").lower() == "true"
        elif sl == "values":
            for val in sub:
                if _local(val.tag) != "value":
                    continue
                unit = okei_code = None
                quality = None
                concrete: list[float] = []
                ranges: list[dict] = []
                for el in val:
                    el_l = _local(el.tag)
                    if el_l == "qualityDescription" and el.text:
                        quality = el.text.strip()
                    elif el_l == "OKEI":
                        for o in el:
                            if _local(o.tag) == "code":
                                okei_code = (o.text or "").strip()
                            elif _local(o.tag) == "name":
                                unit = (o.text or "").strip()
                    elif el_l == "valueSet":
                        for cv in el.iter():
                            if _local(cv.tag) == "concreteValue":
                                n = _num(cv.text)
                                if n is not None:
                                    concrete.append(n)
                    elif el_l == "rangeSet":
                        for vr in el.iter():
                            if _local(vr.tag) != "valueRange":
                                continue
                            r: dict = {}
                            for x in vr:
                                xl = _local(x.tag)
                                if xl == "min":
                                    r["min"] = _num(x.text)
                                elif xl == "max":
                                    r["max"] = _num(x.text)
                                elif xl == "minMathNotation":
                                    r["min_op"] = (x.text or "").strip()
                                elif xl == "maxMathNotation":
                                    r["max_op"] = (x.text or "").strip()
                            ranges.append(r)
                base = {"unit": unit, "okei_code": okei_code}
                if quality:
                    values.append({**base, "kind": "enum", "value": quality})
                for n in concrete:
                    values.append({**base, "kind": "number", "value": str(n), "min": n, "max": n})
                for r in ranges:
                    values.append({**base, "kind": "range", **r})
                if not quality and not concrete and not ranges and unit:
                    values.append({**base, "kind": "any"})
    if not name:
        return None
    return {"name": name, "required": required, "values": values}


def parse_ktru_xml_bytes(data: bytes, conn, max_insert: int | None = None) -> int:
    """Stream-parse one nsiKTRU XML, insert relevant positions."""
    inserted = 0
    context = etree.iterparse(io.BytesIO(data), events=("end",), recover=True)
    for event, elem in context:
        if _local(elem.tag) != "position":
            continue
        # Find data node
        data_el = None
        for child in elem:
            if _local(child.tag) == "data":
                data_el = child
                break
        if data_el is None:
            elem.clear()
            continue

        code = name = okpd2 = okei = status = None
        required = []
        chars = []
        char_values: list[dict] = []

        for child in data_el:
            loc = _local(child.tag)
            if loc == "code":
                code = (child.text or "").strip()
            elif loc == "name":
                name = (child.text or "").strip()
            elif loc == "status":
                status = (child.text or "").strip()
            elif loc == "OKPD2":
                for sub in child:
                    if _local(sub.tag) == "code":
                        okpd2 = (sub.text or "").strip()
            elif loc == "OKEIs":
                for okei_el in child.iter():
                    if _local(okei_el.tag) == "name" and okei_el.text:
                        okei = okei_el.text.strip()
                        break
            elif loc == "characteristics":
                for ch in child:
                    if _local(ch.tag) != "characteristic":
                        continue
                    info = _parse_characteristic(ch)
                    if info:
                        ch_name = info["name"]
                        chars.append({"name": ch_name, "required": info["required"]})
                        if info["required"]:
                            required.append(ch_name)
                        char_values.append(info)

        if status and status.upper() in SKIP_STATUSES:
            elem.clear()
            continue
        if not code or not name:
            elem.clear()
            continue

        domain = detect_domain_from_text(name, okpd2)
        if not domain:
            elem.clear()
            continue

        conn.execute(
            """
            INSERT INTO ktru(code, name, okpd2, domain, okei, required_json, chars_json, name_norm)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(code) DO UPDATE SET
              name=excluded.name, okpd2=excluded.okpd2, domain=excluded.domain,
              required_json=excluded.required_json, chars_json=excluded.chars_json,
              name_norm=excluded.name_norm
            """,
            (
                code,
                name,
                okpd2,
                domain,
                okei,
                json.dumps(required, ensure_ascii=False),
                json.dumps(chars, ensure_ascii=False),
                _norm(name),
            ),
        )
        conn.execute("DELETE FROM ktru_char_values WHERE code=?", (code,))
        for info in char_values:
            for v in info["values"] or [{}]:
                conn.execute(
                    """
                    INSERT INTO ktru_char_values
                    (code, char_name, required, kind, value, vmin, vmax, min_op, max_op, unit, okei_code)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        code,
                        info["name"],
                        1 if info["required"] else 0,
                        v.get("kind", "any"),
                        v.get("value"),
                        v.get("min"),
                        v.get("max"),
                        v.get("min_op"),
                        v.get("max_op"),
                        v.get("unit"),
                        v.get("okei_code"),
                    ),
                )
        inserted += 1
        if inserted % 500 == 0:
            conn.commit()
        if max_insert and inserted >= max_insert:
            elem.clear()
            break
        elem.clear()

    conn.commit()
    return inserted


def ingest_ktru(conn, outer_zip: Path, max_files: int = 40) -> int:
    print(f"[ktru] outer zip: {outer_zip} ({outer_zip.stat().st_size // 1_000_000} MB)")
    total = 0
    with zipfile.ZipFile(outer_zip) as z:
        inners = [n for n in z.namelist() if n.endswith(".zip")]
        # Prefer files that contain actual XML — probe by name order (first ~82 often actual)
        processed = 0
        for inner_name in inners:
            if processed >= max_files:
                break
            raw = z.read(inner_name)
            with zipfile.ZipFile(io.BytesIO(raw)) as z2:
                xmls = z2.namelist()
                actuals = [
                    x
                    for x in xmls
                    if "all_actual" in x.lower() or "all-actual" in x.lower()
                ]
                if not actuals:
                    continue
                n = 0
                for xml_name in actuals:
                    print(f"  parsing {inner_name} -> {xml_name}")
                    n += parse_ktru_xml_bytes(z2.read(xml_name), conn)
                total += n
                processed += 1
                print(f"    +{n} positions (total {total})")
    return total


def seed_ktru_from_portal_if_empty(conn) -> int:
    """Fallback: create pseudo-KTRU rows from distinct STE product type words — last resort."""
    count = conn.execute("SELECT COUNT(*) AS c FROM ktru").fetchone()["c"]
    if count > 0:
        return 0
    print("[fallback] seeding minimal KTRU-like rows from portal STE names")
    # Use common categories from portal_chars
    rows = conn.execute(
        "SELECT DISTINCT domain, category, kpgz_code FROM portal_chars WHERE category IS NOT NULL"
    ).fetchall()
    n = 0
    for r in rows:
        code = f"SEED-{r['kpgz_code'] or n}"
        name = r["category"]
        domain = r["domain"]
        req_rows = conn.execute(
            """
            SELECT char_name FROM portal_chars
            WHERE domain=? AND category=? AND char_type LIKE '%Категореобразующ%'
            ORDER BY char_name LIMIT 10
            """,
            (domain, name),
        ).fetchall()
        # also take a few base chars as "required-ish"
        base = conn.execute(
            """
            SELECT char_name FROM portal_chars
            WHERE domain=? AND category=? ORDER BY id LIMIT 8
            """,
            (domain, name),
        ).fetchall()
        required = [x["char_name"] for x in req_rows] or [x["char_name"] for x in base[:3]]
        chars = [{"name": x["char_name"], "required": x["char_name"] in required} for x in base]
        conn.execute(
            """
            INSERT OR IGNORE INTO ktru(code, name, okpd2, domain, okei, required_json, chars_json, name_norm)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                code,
                name,
                r["kpgz_code"],
                domain,
                "Штука",
                json.dumps(required, ensure_ascii=False),
                json.dumps(chars, ensure_ascii=False),
                _norm(name),
            ),
        )
        n += 1
    conn.commit()
    print(f"  seeded {n}")
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--materials", default=str(ROOT / "_materials"))
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--ktru-files", type=int, default=0, help="Max KTRU zip parts to parse (0 = all, default)")
    ap.add_argument("--ste-limit", type=int, default=20000)
    ap.add_argument("--skip-ktru", action="store_true")
    args = ap.parse_args()

    materials = find_materials_root(Path(args.materials))
    print("Materials root:", materials)
    ensure_processed_dir()
    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()

    conn = connect(db_path)
    init_schema(conn)

    excel = find_excel_files(materials)
    if not excel:
        print("WARNING: no excel files classified")
    for domain, path in excel.items():
        ingest_portal_excel(conn, domain, path, ste_limit=args.ste_limit)

    ktru_n = 0
    if not args.skip_ktru:
        outer = find_ktru_outer_zip(materials)
        if outer:
            ktru_n = ingest_ktru(conn, outer, max_files=args.ktru_files or 10**9)
        else:
            print("WARNING: KTRU zip not found")
    seed_ktru_from_portal_if_empty(conn)

    stats = {
        "ktru": conn.execute("SELECT COUNT(*) c FROM ktru").fetchone()["c"],
        "portal_ste": conn.execute("SELECT COUNT(*) c FROM portal_ste").fetchone()["c"],
        "portal_chars": conn.execute("SELECT COUNT(*) c FROM portal_chars").fetchone()["c"],
        "by_domain": {
            d: conn.execute("SELECT COUNT(*) c FROM ktru WHERE domain=?", (d,)).fetchone()["c"]
            for d in ("furniture", "clothing", "tools")
        },
    }
    set_meta(conn, "stats", stats)
    conn.close()
    print("DONE", json.dumps(stats, ensure_ascii=False, indent=2))
    print("DB:", db_path)


if __name__ == "__main__":
    main()
