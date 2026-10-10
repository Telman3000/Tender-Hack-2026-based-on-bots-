from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import CHAR_ALIASES, DOMAIN_KEYWORDS, UNIT_ALIASES


@dataclass
class RawKV:
    name: str
    value: str
    unit: str | None = None
    # Offsets into the original string, before transliteration and whitespace collapse.
    start: int = -1
    end: int = -1
    polarity: str = "positive"  # positive | negative


@dataclass
class ProductAmbiguity:
    mention: str
    start: int
    end: int
    reason: str = "В одной строке несколько товаров"


@dataclass
class ParseResult:
    product: str
    raw: list[RawKV]
    ambiguities: list[ProductAmbiguity]
    original_text: str = ""


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


_WORD = re.compile(r"[a-zа-яё0-9]+", re.I)

# «без подлокотников» is a rejected feature, not «подлокотники = да».
_NEGATION = re.compile(
    r"\b(?P<marker>без|отсутствует|отсутствуют|не)\s+(?P<noun>[а-яёa-z\-]{3,})",
    re.IGNORECASE,
)
_NEGATION_SKIP = ("менее", "более", "указан", "нужен", "надо", "является")

# Split only on conjunctions. A comma is a size or a characteristic, not a second product.
_PRODUCT_SPLIT = re.compile(r"\s+(?:и|или|а\s+также)\s+|;\s*", re.IGNORECASE)

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


def _needs_translit(text: str) -> bool:
    return not re.search(r"[а-яё]", text, re.I) and bool(re.search(r"[a-z]{3,}", text, re.I))


def _translit_word(w: str) -> str:
    lw = w.lower()
    if not lw.strip() or not re.fullmatch(r"[a-z]+", lw):
        return w if not re.fullmatch(r"\d+x\d+", lw) else lw
    if lw in _UNIT_LAT:
        return _UNIT_LAT[lw]
    r = lw
    for a, b in _TR:
        r = r.replace(a, b)
    if w.isupper() and len(w) <= 5:  # abbreviations: LDSP -> ЛДСП
        return r.upper()
    return r


def _translit_chars(text: str) -> tuple[str, list[int], list[int]]:
    """Transliterate Latin text. Each output char remembers its source range in `text`."""
    n = len(text)
    if not _needs_translit(text):
        return text, list(range(n)), [i + 1 for i in range(n)]
    out: list[str] = []
    origin_start: list[int] = []
    origin_end: list[int] = []
    pos = 0
    for w in re.split(r"(\s+)", text):
        if w == "":
            continue
        start, end = pos, pos + len(w)
        pos = end
        piece = _translit_word(w)
        same = piece == w
        for i, ch in enumerate(piece):
            out.append(ch)
            if same:
                origin_start.append(start + i)
                origin_end.append(start + i + 1)
            else:
                origin_start.append(start)
                origin_end.append(end)
    return "".join(out), origin_start, origin_end


def _collapse_ws(text: str, origin_start: list[int], origin_end: list[int]) -> tuple[str, list[int], list[int]]:
    """Same normalization as the historical parser: strip, then one space between tokens."""
    n = len(text)
    i = 0
    while i < n and text[i].isspace():
        i += 1
    j = n
    while j > i and text[j - 1].isspace():
        j -= 1
    out: list[str] = []
    ns: list[int] = []
    ne: list[int] = []
    k = i
    while k < j:
        if text[k].isspace():
            run = k
            while k < j and text[k].isspace():
                k += 1
            out.append(" ")
            ns.append(origin_start[run])
            ne.append(origin_end[k - 1])
        else:
            out.append(text[k])
            ns.append(origin_start[k])
            ne.append(origin_end[k])
            k += 1
    return "".join(out), ns, ne


def _prepare(original: str) -> tuple[str, list[int], list[int]]:
    """Working text plus a map back to `original` (before transliteration)."""
    folded, origin_start, origin_end = _translit_chars(original or "")
    return _collapse_ws(folded, origin_start, origin_end)


def _span(start: int, end: int, origin_start: list[int], origin_end: list[int]) -> tuple[int, int]:
    if start < 0 or end <= start or not origin_start:
        return -1, -1
    end = min(end, len(origin_start))
    start = min(start, len(origin_start) - 1)
    if end <= start:
        return -1, -1
    return origin_start[start], origin_end[end - 1]


def translit_if_latin(text: str) -> str:
    """'Stol ofisnyj LDSP 1200x750 mm' -> 'стол офисный ЛДСП 1200x750 мм' (only for text without Cyrillic)."""
    return _translit_chars(text or "")[0]


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
            out.append(RawKV(
                name=n, value=v.replace(",", "."), unit=unit,
                start=m.start(), end=m.end(),
            ))
    return out


def _product_stems() -> list[str]:
    stems = [k.replace("ё", "е") for kws in DOMAIN_KEYWORDS.values() for k in kws]
    return sorted(set(stems), key=len, reverse=True)


def _segment_stem(segment: str) -> str | None:
    for m in _WORD.finditer(segment):
        word = m.group().lower().replace("ё", "е")
        for stem in _product_stems():
            if word.startswith(stem):
                return stem
    return None


def _ambiguities(working: str, origin_start: list[int], origin_end: list[int]) -> list[ProductAmbiguity]:
    """Two product heads joined by «и / или / а также / ;» are not one card."""
    parts: list[tuple[str, int, int]] = []
    last = 0
    for m in _PRODUCT_SPLIT.finditer(working):
        parts.append((working[last:m.start()], last, m.start()))
        last = m.end()
    parts.append((working[last:], last, len(working)))
    hits: list[ProductAmbiguity] = []
    stems: set[str] = set()
    for seg, a, b in parts:
        stem = _segment_stem(seg)
        if not stem:
            continue
        stems.add(stem)
        mention = seg.strip()
        lead = len(seg) - len(seg.lstrip())
        trail = len(seg) - len(seg.rstrip())
        sa, sb = _span(a + lead, b - trail, origin_start, origin_end)
        hits.append(ProductAmbiguity(mention=mention, start=sa, end=sb))
    if len(stems) < 2 or len(hits) < 2:
        return []
    return hits


def _extract(text: str, domain: str | None) -> list[RawKV]:
    found: list[RawKV] = []
    seen: set[tuple[str, str, str]] = set()

    def add(
        name: str,
        value: str,
        unit: str | None = None,
        start: int = -1,
        end: int = -1,
        polarity: str = "positive",
    ) -> None:
        name = name.strip()
        value = value.strip(" .;")
        if not name or not value:
            return
        key = (name.lower(), value.lower(), polarity)
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
                start=start,
                end=end,
                polarity=polarity,
            )
        )

    if "|" in text:
        pos = 0
        for part in text.split("|"):
            raw_start = pos
            raw_end = pos + len(part)
            pos = raw_end + 1
            stripped = part.strip()
            lead = len(part) - len(part.lstrip())
            m = re.match(
                r"^(?P<name>[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9\s/\-]{0,40}?)\s+"
                r"(?P<rest>.+)$",
                stripped,
            )
            if m:
                add(m.group("name"), m.group("rest"), start=raw_start + lead, end=raw_end - (len(part) - len(part.rstrip())))

    for m in _KV_COLON.finditer(text):
        add(m.group("name"), m.group("value"), start=m.start(), end=m.end())

    dim_spans = [(m.start(), m.end()) for m in _DIMS.finditer(text)] if domain == "furniture" else []
    if domain == "furniture":
        for kv in composite_dimensions(text):
            add(kv.name, kv.value, kv.unit, start=kv.start, end=kv.end)

    def _inside_composite(a: int, b: int) -> bool:
        return any(a < end and b > start for start, end in dim_spans)

    for m in _NUM_UNIT.finditer(text):
        if _inside_composite(m.start(), m.end()):
            continue
        if re.match(r"\s*[хxX×*]\s*\d", text[m.end():]):
            continue  # part of a composite value («17х19», «размер 1200х750»)
        add(m.group("label"), m.group("value"), m.group("unit"), start=m.start(), end=m.end())

    for m in _PERCENT.finditer(text):
        mat = (m.group("m1") or m.group("m2") or "").strip()
        add(f"Содержание {mat.lower()}", m.group("p1") or m.group("p2"), "%", start=m.start(), end=m.end())

    for m in _COLOR.finditer(text):
        add("Цвет", m.group("value"), start=m.start(), end=m.end())

    for m in _MATERIAL.finditer(text):
        add("Материал", m.group("value"), start=m.start(), end=m.end())

    for token in ("ДСП", "МДФ", "ЛДСП"):
        if any(x.name.lower() == "материал" for x in found):
            break
        hit = re.search(rf"\b{token}\b", text, re.I)
        if hit:
            add("Материал", token, start=hit.start(), end=hit.end())

    for m in _NEGATION.finditer(text):
        noun = m.group("noun")
        if noun.lower().replace("ё", "е").startswith(_NEGATION_SKIP):
            continue
        add(noun, "нет", start=m.start(), end=m.end(), polarity="negative")

    return found


def parse_text(text: str, domain: str | None = None) -> ParseResult:
    """Parse `text` as the user typed it. Spans point into that string, before transliteration."""
    original = text or ""
    working, origin_start, origin_end = _prepare(original)
    ambiguities = _ambiguities(working, origin_start, origin_end)
    if ambiguities:
        return ParseResult(product="", raw=[], ambiguities=ambiguities, original_text=original)
    found = _extract(working, domain)
    for kv in found:
        kv.start, kv.end = _span(kv.start, kv.end, origin_start, origin_end)
    return ParseResult(
        product=guess_product_name(working),
        raw=found,
        ambiguities=[],
        original_text=original,
    )


def parse_free_text(text: str, domain: str | None = None) -> tuple[str, list[RawKV]]:
    result = parse_text(text, domain)
    if result.ambiguities:
        return "", []
    return result.product, result.raw
