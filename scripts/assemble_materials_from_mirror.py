"""Assemble hackathon-like _materials layout from keysystems nsiKTRUNewActive parts.

Yandex Disk may be unavailable; this builds КТРУ/xml.zip with inner zips whose XML
files are renamed to *all_actual* so build_index.is_actual_file accepts them.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "_materials" / "ktru_parts"
OUT_ZIP = ROOT / "_materials" / "КТРУ" / "КТРУ xml.zip"


def main() -> None:
    parts = sorted(PARTS.glob("nsiKTRUs_all_*.xml.zip"))
    if not parts:
        raise SystemExit(f"No parts in {PARTS}")
    OUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as outer:
        for i, part in enumerate(parts):
            with zipfile.ZipFile(part) as zin:
                xml_names = [n for n in zin.namelist() if n.lower().endswith(".xml")]
                if not xml_names:
                    continue
                raw_xml = zin.read(xml_names[0])
                actual_name = f"nsiKTRUNew_all_actual_{i:03d}.xml"
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as inner:
                    inner.writestr(actual_name, raw_xml)
                inner_name = f"part_{i:03d}.zip"
                outer.writestr(inner_name, buf.getvalue())
    print(f"Wrote {OUT_ZIP} ({OUT_ZIP.stat().st_size // 1_000_000} MB) from {len(parts)} parts")


if __name__ == "__main__":
    main()
