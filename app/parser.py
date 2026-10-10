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
    r"напряжение|объ[её]м|размер)\s+"
    r"(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>мм|см|м|кг|г|гр|шт|мл|л|кВт|Вт|вт|В|А|%)?(?![а-яa-z])",
    re.IGNORECASE,
)

_MATS = r"хлопок|хлопка|полиэстер|полиэстера|шерсть|шерсти|вискоза|вискозы|эластан|эластана|лен|льна|нейлон|нейлона|полиамид|акрил"
_PERCENT = re.compile(
    rf"(?:(?P<m1>{_MATS})\s*(?P<p1>\d+(?:[.,]\d+)?)\s*%|(?P<p2>\d+(?:[.,]\d+)?)\s*%\s*(?P<m2>{_MATS}))",
    re.I,
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


_WORD = re.compile(r"[a-zа-яё0-9]+", re.I)

# tokens that flip a keyword away from our scope ("музыкальных инструментов")
_NEGATIVE = {"tools": ("музыкальн",)}

_CHAR_WORDS = (
    "высота|ширина|глубина|длина|масса|вес|толщина|диаметр|мощность|напряжение|"
    "объем|объём|размер|материал|цвет|тип|вид|состав|емкость|ёмкость|количество|"
    "артикул|модель|производитель|бренд|страна"
)
_HEAD_CUT = re.compile(
    rf"[|:;,(]|\b(?:{_CHAR_WORDS})\b|\b(?:из|для|с|со|на)\b\s+\S+\s*\d|\d",
    re.I,
)


def words(text: str) -> list[str]:
    return [w.lower().replace("ё", "е") for w in _WORD.findall(text or "")]


def domain_scores(text: str) -> dict[str, int]:
    """Keyword stems matched at word start only ('стол' ≠ 'настольный', 'ключ' ≠ 'включая')."""
    ws = words(text)
    scores: dict[str, int] = {}
    for domain, kws in DOMAIN_KEYWORDS.items():
        kws_n = [k.replace("ё", "е") for k in kws]
        n = sum(1 for w in ws for k in kws_n if w.startswith(k))
        neg = _NEGATIVE.get(domain, ())
        if neg and any(w.startswith(x) for w in ws for x in neg):
            n = 0
        scores[domain] = n
    return scores


def detect_domain(text: str, hint: str | None = None) -> str | None:
    if hint and hint in DOMAIN_KEYWORDS:
        return hint
    head = guess_product_name(text)
    for chunk in (head, text):
        scores = domain_scores(chunk)
        best = max(scores, key=scores.get)
        if scores[best] > 0:
            return best
    return None


def guess_product_name(text: str) -> str:
    """Head noun phrase: text before the first characteristic marker / number, max 6 words."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    head = _HEAD_CUT.split(text, maxsplit=1)[0].strip(" ,.-")
    ws = head.split()
    if len(ws) > 6:
        head = " ".join(ws[:6])
    head = re.sub(r"(?:\s+(?:из|для|с|со|на|и|в))+$", "", head, flags=re.I)
    return head or " ".join(text.split()[:4])


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
            r"^(?P<v>\d+(?:[.,]\d+)?)\s*(?P<u>мм|см|м|кг|г|гр|шт|мл|л|кВт|Вт|вт|В|А|%)$",
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

    for m in _PERCENT.finditer(text):
        mat = (m.group("m1") or m.group("m2") or "").strip()
        add(f"Содержание {mat.lower()}", m.group("p1") or m.group("p2"), "%")

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
