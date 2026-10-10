from __future__ import annotations

import re
import sqlite3

from rapidfuzz import fuzz, process

from app.config import CHAR_ALIASES
from app.models import CharSource, Issue, ParsedCharacteristic
from app.parser import RawKV, canonicalize_name, canonicalize_unit


def _load_portal_char_names(conn: sqlite3.Connection, domain: str | None) -> list[str]:
    if domain:
        rows = conn.execute(
            "SELECT DISTINCT char_name FROM portal_chars WHERE domain=? AND char_name IS NOT NULL",
            (domain,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT char_name FROM portal_chars WHERE char_name IS NOT NULL"
        ).fetchall()
    return [r["char_name"] for r in rows if r["char_name"]]


def _load_ktru_char_names(conn: sqlite3.Connection, codes: list[str] | None = None) -> dict[str, str]:
    """Return alias->canonical from required chars of candidate codes."""
    mapping: dict[str, str] = {}
    if not codes:
        return mapping
    qmarks = ",".join("?" * len(codes))
    rows = conn.execute(
        f"SELECT required_json, chars_json FROM ktru WHERE code IN ({qmarks})",
        codes,
    ).fetchall()
    import json

    for row in rows:
        for blob in (row["required_json"], row["chars_json"]):
            if not blob:
                continue
            try:
                items = json.loads(blob)
            except Exception:
                continue
            for it in items:
                name = it if isinstance(it, str) else it.get("name")
                if name:
                    mapping[name.lower()] = name
    return mapping


def unify_characteristics(
    conn: sqlite3.Connection,
    raw: list[RawKV],
    domain: str | None,
    candidate_codes: list[str] | None = None,
) -> tuple[list[ParsedCharacteristic], list[Issue]]:
    portal_names = _load_portal_char_names(conn, domain)
    ktru_map = _load_ktru_char_names(conn, candidate_codes)
    issues: list[Issue] = []
    out: list[ParsedCharacteristic] = []

    for item in raw:
        canon = canonicalize_name(item.name)
        unit = canonicalize_unit(item.unit)
        source = CharSource.USER
        notes = None
        confidence = 0.7

        # 1) КТРУ эталон
        if canon.lower() in ktru_map:
            canon = ktru_map[canon.lower()]
            source = CharSource.KTRU
            confidence = 0.95
            notes = "Сопоставлено со справочником КТРУ"
        elif item.name.lower() in CHAR_ALIASES:
            canon = CHAR_ALIASES[item.name.lower()]
            # still try portal
            source = CharSource.PORTAL
            confidence = 0.85
            notes = "Унифицировано по словарю алиасов"
        elif portal_names:
            match = process.extractOne(
                canon,
                portal_names,
                scorer=fuzz.WRatio,
                score_cutoff=80,
            )
            if match:
                canon = match[0]
                source = CharSource.PORTAL
                confidence = match[1] / 100.0
                notes = f"Сопоставлено с характеристикой портала (score={match[1]})"
            else:
                source = CharSource.NEW
                confidence = 0.55
                notes = "Новое свойство (нет в КТРУ/портале) — сохранено как пользовательское"
                issues.append(
                    Issue(
                        kind="new_property",
                        message=f"Характеристика «{item.name}» не найдена в КТРУ и выгрузках — заведена как новая",
                        field=canon,
                        suggestion="Проверьте формулировку; при повторении используйте единое имя",
                    )
                )

        # Unit / value sanity
        value = item.value
        if unit in {"мм", "см", "м"} and re.fullmatch(r"\d+(?:\.\d+)?", value or ""):
            num = float(value)
            # absurd height for furniture in meters typed as meters when meant cm
            if unit == "м" and canon.lower() in {"высота", "ширина", "глубина", "длина"} and num > 5:
                issues.append(
                    Issue(
                        kind="unit",
                        message=f"Подозрительное значение {value} {unit} для «{canon}»",
                        field=canon,
                        suggestion="Возможно, имелись в виду см или мм",
                    )
                )
            if unit == "мм" and canon.lower() == "высота" and num > 5000:
                issues.append(
                    Issue(
                        kind="mismatch",
                        message=f"Высота {value} мм выглядит нереалистично для мебели/инструмента",
                        field=canon,
                        suggestion="Проверьте единицу измерения и значение",
                    )
                )

        # RAM-like absurd example from briefing
        if "оператив" in canon.lower() or "память" in item.name.lower():
            if re.search(r"\b2\b", value) and "гб" in (value + (unit or "")).lower():
                issues.append(
                    Issue(
                        kind="mismatch",
                        message="2 ГБ оперативной памяти для современного ноутбука — подозрительно мало",
                        field=canon,
                        suggestion="Уточните объём ОЗУ",
                    )
                )

        out.append(
            ParsedCharacteristic(
                raw_name=item.name,
                canonical_name=canon,
                value=value,
                unit=unit,
                source=source,
                confidence=confidence,
                notes=notes,
            )
        )

    return out, issues
