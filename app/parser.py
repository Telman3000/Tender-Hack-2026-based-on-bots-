from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import CHAR_ALIASES, DOMAIN_KEYWORDS, UNIT_ALIASES


@dataclass
class RawKV:
    name: str
    value: str
    unit: str | None = None


_KV_COLON = re.compile(
    r"(?P<name>[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9\s/\-]{1,30}?)\s*[:：]\s*"
    r"(?P<value>[^,;|]+)",
    re.IGNORECASE,
)

_NUM_UNIT = re.compile(
    r"(?P<label>высота|ширина|глубина|длина|масса|вес|толщина|диаметр|мощность|"
    r"объ[её]м|размер)\s+"
    r"(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>мм|см|м|кг|г|гр|шт|л|Вт|вт|В|А)?",
    re.IGNORECASE,
)

_COLOR = re.compile(
    r"\bцвет(?:а|ом)?\s+(?P<value>[а-яёa-z\-]+)",
    re.IGNORECASE,
)

_MATERIAL = re.compile(
    r"\b(материал(?:а)?|из)\s+(?P<value>ДСП|МДФ|металл(?:а|ический)?|дерев(?:о|а)|"
    r"пластик(?:а)?|стекл[оа]|кож[аи]|ткан[ьи]|полиэстер|хлопок|сталь)",
    re.IGNORECASE,
)


def detect_domain(text: str, hint: str | None = None) -> str | None:
    if hint and hint in DOMAIN_KEYWORDS:
        return hint
    low = text.lower()
    scores = {
        domain: sum(1 for kw in kws if kw in low)
        for domain, kws in DOMAIN_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def guess_product_name(text: str) -> str:
    """Take leading chunk before first clear characteristic marker."""
    cut = re.split(
        r"[|:;]|\bвысота\b|\bширина\b|\bматериал\b|\bцвет\b|\bвес\b|\bмасса\b",
        text,
        maxsplit=1,
        flags=re.I,
    )
    head = cut[0].strip(" ,.-")
    if len(head) > 120:
        head = head[:120].rsplit(" ", 1)[0]
    return head or text[:80]


def canonicalize_name(name: str) -> str:
    key = name.strip().lower().replace("ё", "е")
    return CHAR_ALIASES.get(key, name.strip().capitalize() if name.islower() else name.strip())


def canonicalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    return UNIT_ALIASES.get(unit.strip().lower(), unit.strip())


def parse_free_text(text: str) -> tuple[str, list[RawKV]]:
    text = re.sub(r"\s+", " ", text.strip())
    product = guess_product_name(text)
    found: list[RawKV] = []
    seen: set[tuple[str, str]] = set()

    def add(name: str, value: str, unit: str | None = None) -> None:
        name = name.strip()
        value = value.strip(" .;")
        if not name or not value:
            return
        key = (name.lower(), value.lower())
        if key in seen:
            return
        seen.add(key)
        m = re.match(
            r"^(?P<v>\d+(?:[.,]\d+)?)\s*(?P<u>мм|см|м|кг|г|гр|шт|л|Вт|вт|В|А)$",
            value,
            re.I,
        )
        if m and not unit:
            value, unit = m.group("v"), m.group("u")
        found.append(
            RawKV(
                name=name,
                value=value.replace(",", "."),
                unit=canonicalize_unit(unit),
            )
        )

    # Pattern: "Ключ значение |" portal style
    if "|" in text:
        for part in text.split("|"):
            part = part.strip()
            m = re.match(
                r"^(?P<name>[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9\s/\-]{0,40}?)\s+"
                r"(?P<rest>.+)$",
                part,
            )
            if m:
                add(m.group("name"), m.group("rest"))

    for m in _KV_COLON.finditer(text):
        add(m.group("name"), m.group("value"))

    for m in _NUM_UNIT.finditer(text):
        add(m.group("label"), m.group("value"), m.group("unit"))

    for m in _COLOR.finditer(text):
        add("Цвет", m.group("value"))

    for m in _MATERIAL.finditer(text):
        add("Материал", m.group("value"))

    for token in ("ДСП", "МДФ", "ЛДСП"):
        if re.search(rf"\b{token}\b", text, re.I) and not any(
            x.name.lower() == "материал" for x in found
        ):
            add("Материал", token)

    return product, found
