from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import CHAR_ALIASES, DOMAIN_KEYWORDS, UNIT_ALIASES
from app.morph import adjective, genitive_noun


@dataclass
class RawKV:
    name: str
    value: str
    unit: str | None = None
    text: str | None = None


_KV_COLON = re.compile(
    r"(?P<name>[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9\s/\-]{1,30}?)\s*[:：]\s*"
    r"(?P<value>[^,;|]+)",
    re.IGNORECASE,
)

_NUM_UNIT = re.compile(
    r"(?P<label>высота|ширина|глубина|длина|масса|вес|толщина|диаметр|мощность|"
    r"напряжение|объ[её]м|размер|рост)\s+"
    r"(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>миллиметр\w*|сантиметр\w*|метр\w*|килограмм\w*|грамм\w*|литр\w*|ватт\w*|вольт\w*|"
    r"мм|см|м|кг|г|гр|шт|мл|л|кВт|Вт|вт|В|А|%)?(?![а-яa-z\d])",
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


_MAT_VALUE = r"(?P<value>(?!(?:из|для|и|с)\b)[а-яёa-z][а-яёa-z\-]{2,})(?:\s+(?P<next>[а-яё]+))?"
_PART_MATERIAL = re.compile(
    rf"\bматериала?\s+(?P<part>[а-яё]+)(?:\s*[:\-–—]\s*|\s+){_MAT_VALUE}", re.IGNORECASE,
)
_ANY_MATERIAL = re.compile(rf"\bматериал\s+{_MAT_VALUE}", re.IGNORECASE)


def _material_value(m: re.Match) -> str:
    value, nxt = m.group("value"), m.group("next")
    return f"{value} {nxt}" if nxt and adjective(value) else value


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


_TR = [("shch", "щ"), ("sch", "щ"), ("yo", "ё"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("ch", "ч"),
       ("sh", "ш"), ("yu", "ю"), ("ya", "я"), ("yj", "ый"), ("ij", "ий"), ("iy", "ий"), ("yy", "ый"),
       ("a", "а"), ("b", "б"), ("v", "в"), ("g", "г"), ("d", "д"), ("e", "е"), ("z", "з"), ("i", "и"),
       ("j", "й"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"),
       ("s", "с"), ("t", "т"), ("u", "у"), ("f", "ф"), ("h", "х"), ("c", "ц"), ("y", "ы"), ("w", "в"), ("x", "кс")]
_UNIT_LAT = {"mm": "мм", "cm": "см", "m": "м", "kg": "кг", "g": "г", "vt": "Вт", "w": "Вт", "v": "В", "l": "л"}


def translit_if_latin(text: str) -> str:
    """'Stol ofisnyj LDSP 1200x750 mm' -> 'стол офисный ЛДСП 1200x750 мм' (only for text without Cyrillic)."""
    if re.search(r"[а-яё]", text, re.I) or not re.search(r"[a-z]{3,}", text, re.I):
        return text
    out = []
    for w in re.split(r"(\s+)", text):
        lw = w.lower()
        if not lw.strip() or not re.fullmatch(r"[a-z]+", lw):
            out.append(w if not re.fullmatch(r"\d+x\d+", lw) else lw)
            continue
        if lw in _UNIT_LAT:
            out.append(_UNIT_LAT[lw])
            continue
        if w.isupper() and len(w) <= 5:  # abbreviations: LDSP -> ЛДСП
            r = lw
            for a, b in _TR:
                r = r.replace(a, b)
            out.append(r.upper())
            continue
        r = lw
        for a, b in _TR:
            r = r.replace(a, b)
        out.append(r)
    return "".join(out)


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


_X = r"\s*[хxX×*]\s*"
_DIMS = re.compile(
    rf"(?:(?P<hint>[ШшДдГгВвWwLlDdHh]{_X}[ШшДдГгВвWwLlDdHh](?:{_X}[ШшДдГгВвWwLlDdHh])?)\s*[:=-]?\s*)?"
    rf"(?<![\d.,])(?P<a>\d+(?:[.,]\d+)?){_X}(?P<b>\d+(?:[.,]\d+)?)(?:{_X}(?P<c>\d+(?:[.,]\d+)?))?"
    r"\s*(?P<unit>мм|см|м|mm|cm|m)?(?![а-яa-z\d])",
    re.I,
)
_HINT = {"ш": "Ширина", "w": "Ширина", "г": "Глубина", "d": "Глубина", "в": "Высота", "h": "Высота",
         "д": "Длина", "l": "Длина"}


def composite_dimensions(text: str) -> list[RawKV]:
    """«1200х700х750 мм», «ШхГхВ 1200x600x750» -> Ширина/Глубина/Высота (furniture only)."""
    out: list[RawKV] = []
    for m in _DIMS.finditer(text):
        vals = [v for v in (m.group("a"), m.group("b"), m.group("c")) if v]
        if m.group("hint"):
            letters = [x.lower() for x in re.findall(r"[ШшДдГгВвWwLlDdHh]", m.group("hint"))]
            names = [_HINT.get(x, "Размер") for x in letters]
        else:
            names = ["Ширина", "Глубина", "Высота"][: len(vals)]
        unit = canonicalize_unit(m.group("unit")) if m.group("unit") else None
        for n, v in zip(names, vals):
            out.append(RawKV(name=n, value=v.replace(",", "."), unit=unit))
    return out


def parse_free_text(text: str, domain: str | None = None) -> tuple[str, list[RawKV]]:
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

    for m in _PART_MATERIAL.finditer(text):
        if genitive_noun(m.group("part")):
            add(f"Материал {m.group('part').lower()}", _material_value(m))

    if domain == "furniture":
        for kv in composite_dimensions(text):
            add(kv.name, kv.value, kv.unit)
        text_for_num = _DIMS.sub(" ", text)
    else:
        text_for_num = text
    for m in _NUM_UNIT.finditer(text_for_num):
        if re.match(r"\s*[хxX×*]\s*\d", text_for_num[m.end():]):
            continue  # part of a composite value («17х19», «размер 1200х750»)
        add(m.group("label"), m.group("value"), m.group("unit"))

    for m in _PERCENT.finditer(text):
        mat = (m.group("m1") or m.group("m2") or "").strip()
        add(f"Содержание {mat.lower()}", m.group("p1") or m.group("p2"), "%")

    for m in _COLOR.finditer(text):
        add("Цвет", m.group("value"))

    for m in _MATERIAL.finditer(text):
        add("Материал", m.group("value"))

    if not any(x.name == "Материал" for x in found):
        for m in _ANY_MATERIAL.finditer(text):
            if not genitive_noun(m.group("value")):
                add("Материал", _material_value(m))

    for token in ("ДСП", "МДФ", "ЛДСП"):
        if re.search(rf"\b{token}\b", text, re.I) and not any(
            x.name.lower().startswith("материал") for x in found
        ):
            add("Материал", token)

    return product, found
