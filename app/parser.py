from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import CHAR_ALIASES, DOMAIN_KEYWORDS, UNIT_ALIASES


@dataclass
class RawKV:
    name: str
    value: str
    unit: str | None = None
    bound: str | None = None  # «не менее» / «не более»: число есть, точного значения нет


_KV_COLON = re.compile(
    r"(?P<name>[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9\s/\-]{1,30}?)\s*[:：]\s*"
    r"(?P<value>[^,;|]+)",
    re.IGNORECASE,
)

_NUM_UNIT = re.compile(
    r"(?P<label>высот(?:а|ой)|ширин(?:а|ой)|глубин(?:а|ой)|длин(?:а|ой)|масс(?:а|ой)|вес(?:ом)?|"
    r"толщин(?:а|ой)|диаметр(?:ом)?|мощност(?:ь|ью)|напряжени(?:е|ем)|объ[её]м(?:ом)?|"
    r"размер(?:ом)?|рост(?:ом)?)\s+"
    r"(?:(?P<op>не\s+менее|не\s+более|не\s+меньше|не\s+больше)\s+)?"
    r"(?P<value>[-−–]?\d+(?:[.,]\d+)?(?:\s*[-–—]\s*\d+(?:[.,]\d+)?)?)\s*"
    r"(?P<unit>миллиметр\w*|сантиметр\w*|метр\w*|килограмм\w*|тонна\w*|тонн\w*|грамм\w*|литр\w*|ватт\w*|вольт\w*|"
    r"мм|см|м|кг|г|гр|шт|мл|л|кВт|Вт|вт|В|А|т|%)?(?![а-яa-z\d])",
    re.IGNORECASE,
)
# «48 размер», «170 рост» — число стоит перед названием
_NUM_UNIT_REV = re.compile(
    r"(?<![\d.,])(?P<value>\d+(?:[.,]\d+)?(?:\s*[-–—]\s*\d+(?:[.,]\d+)?)?)\s+"
    r"(?P<label>размер|рост)\b",
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
_COLOR_STEMS = (
    ("черн", "черный"), ("бел", "белый"), ("сер", "серый"), ("син", "синий"),
    ("красн", "красный"), ("зелен", "зеленый"), ("желт", "желтый"),
    ("коричнев", "коричневый"), ("бежев", "бежевый"), ("оранж", "оранжевый"),
    ("фиолетов", "фиолетовый"), ("голуб", "голубой"), ("розов", "розовый"),
)
_COLOR_REV = re.compile(
    r"\b(?P<value>черн\w*|бел\w*|сер\w*|син\w*|красн\w*|зелен\w*|желт\w*|"
    r"коричнев\w*|бежев\w*|оранж\w*|фиолетов\w*|голуб\w*|розов\w*)\s+цвет\b",
    re.IGNORECASE,
)
_COLOR_BARE = re.compile(
    r"\b(?P<value>черн(?:ый|ая|ое|ые|ой|ого|ым)|бел(?:ый|ая|ое|ые|ой)|"
    r"сер(?:ый|ая|ое|ые|ой)|син(?:ий|яя|ее|ие)|красн(?:ый|ая|ое|ые|ой)|"
    r"зелен(?:ый|ая|ое|ые)|желт(?:ый|ая|ое|ые)|коричнев(?:ый|ая|ое|ые)|бежев(?:ый|ая|ое|ые))\b",
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


_TR = [("shch", "щ"), ("sch", "щ"), ("yo", "ё"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("ch", "ч"),
       ("sh", "ш"), ("yu", "ю"), ("ya", "я"), ("yj", "ый"), ("ij", "ий"), ("iy", "ий"), ("yy", "ый"),
       ("yi", "ый"),
       ("a", "а"), ("b", "б"), ("v", "в"), ("g", "г"), ("d", "д"), ("e", "е"), ("z", "з"), ("i", "и"),
       ("j", "й"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"),
       ("s", "с"), ("t", "т"), ("u", "у"), ("f", "ф"), ("h", "х"), ("c", "ц"), ("y", "ы"), ("w", "в"), ("x", "кс")]
_UNIT_LAT = {"mm": "мм", "cm": "см", "m": "м", "kg": "кг", "g": "г", "vt": "Вт", "w": "Вт", "v": "В", "l": "л"}
# English product words. Letter-by-letter translit turns "desk" into «деск» and "laminate" into «ламинатор».
_EN_WORD = {
    "office": "офисный", "desk": "стол", "table": "стол", "chair": "стул",
    "hammer": "молоток", "drill": "дрель", "screwdriver": "отвертка",
    "shirt": "футболка", "jacket": "куртка", "wardrobe": "шкаф",
    "height": "высота", "width": "ширина", "depth": "глубина",
    "weight": "масса", "mass": "масса", "power": "мощность", "size": "размер",
    "laminate": "лдсп", "laminated": "лдсп",
    "black": "черный", "grey": "серый", "gray": "серый", "red": "красный",
    "color": "цвет", "colour": "цвет",
}


_LATIN_SKIP = {"drop", "table", "select", "insert", "update", "delete", "where", "users", "from", "union", "alter"}


def _translit_word(w: str) -> str:
    lw = w.lower()
    if lw in _UNIT_LAT:
        return _UNIT_LAT[lw]
    if lw in _EN_WORD:
        return _EN_WORD[lw]
    if w.isupper() and len(w) <= 5:  # abbreviations: LDSP -> ЛДСП
        r = lw
        for a, b in _TR:
            r = r.replace(a, b)
        return r.upper()
    r = lw
    for a, b in _TR:
        r = r.replace(a, b)
    return r


def translit_if_latin(text: str) -> str:
    """'Stol ofisnyj LDSP' -> 'стол офисный ЛДСП'. A latin word inside Russian ('pismennyi') is transliterated too."""
    if not text or not re.search(r"[a-z]{3,}", text, re.I):
        return text
    mixed = bool(re.search(r"[а-яё]", text, re.I))

    def one(w: str) -> str:
        if mixed and (len(w) < 6 or w.lower() in _LATIN_SKIP):
            return w
        return _translit_word(w)

    out = []
    for w in re.split(r"(\s+)", text):
        lw = w.lower()
        if not lw.strip() or not re.fullmatch(r"[a-z]+", lw):
            out.append(w if not re.fullmatch(r"\d+x\d+", lw) else lw)
            continue
        out.append(one(w))
    return "".join(out)


_ONES = {
    "ноль": 0, "один": 1, "одна": 1, "одно": 1, "одну": 1,
    "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
}
_TEENS = {
    "десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
    "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19,
}
_TENS = {
    "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
}
_HUNDREDS = {
    "сто": 100, "двести": 200, "триста": 300, "четыреста": 400, "пятьсот": 500,
    "шестьсот": 600, "семьсот": 700, "восемьсот": 800, "девятьсот": 900,
}
_THOUSANDS = {"тысяча": 1000, "тысячи": 1000, "тысяч": 1000}
_NUMWORDS = {**_ONES, **_TEENS, **_TENS, **_HUNDREDS, **_THOUSANDS}
_UNIT_WORD = {
    "миллиметр": "мм", "миллиметра": "мм", "миллиметров": "мм", "миллиметре": "мм",
    "сантиметр": "см", "сантиметра": "см", "сантиметров": "см",
    "метр": "м", "метра": "м", "метров": "м",
    "килограмм": "кг", "килограмма": "кг", "килограммов": "кг",
    "грамм": "г", "грамма": "г", "граммов": "г",
    "литр": "л", "литра": "л", "литров": "л",
    "ватт": "Вт", "ватта": "Вт",
    "вольт": "В", "вольта": "В", "вольтов": "В",
}
_HALF_WORDS = (
    (re.compile(r"\bполкилограмма\b", re.I), "0.5 кг"),
    (re.compile(r"\bполкило\b", re.I), "0.5 кг"),
    (re.compile(r"\bполметра\b", re.I), "0.5 м"),
    (re.compile(r"\bполлитра\b", re.I), "0.5 л"),
)
_NA_DIMS = re.compile(
    r"(?<![\d.,])(?P<a>\d+(?:[.,]\d+)?)\s+на\s+(?P<b>\d+(?:[.,]\d+)?)\s+на\s+(?P<c>\d+(?:[.,]\d+)?)"
    r"(?:\s*(?P<unit>мм|см|м))?(?![а-яa-z\d])",
    re.I,
)
_LAMINATE = re.compile(r"ламинированн\w*\s+плит\w*", re.I)
_BARE_MAT = re.compile(r"\b(?P<value>полиэстер\w*|хлопок|хлопка|кож[аи])\b", re.I)
_BARE_Q = re.compile(
    r"(?<![\d\w])(?P<value>\d+(?:[.,]\d+)?)\s*(?:(?P<rpm>об/мин)|(?P<volt>В)(?![а-яa-zА-Я]))",
    re.I,
)
_FOLD = str.maketrans("０１２３４５６７８９％", "0123456789%")


def _ru_number(words: list[str]) -> int | None:
    total = current = 0
    for w in words:
        if w in _HUNDREDS:
            current += _HUNDREDS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w in _TEENS:
            current += _TEENS[w]
        elif w in _ONES:
            current += _ONES[w]
        elif w in _THOUSANDS:
            total += (current or 1) * 1000
            current = 0
        else:
            return None
    return total + current


def _words_to_numbers(text: str) -> str:
    """«семьсот пятьдесят миллиметров» -> «750 мм», «полкилограмма» -> «0.5 кг»."""
    for rx, repl in _HALF_WORDS:
        text = rx.sub(repl, text)
    parts = re.split(r"(\s+)", text)
    out: list[str] = []
    i = 0
    while i < len(parts):
        token = parts[i]
        key = token.lower().replace("ё", "е")
        if key not in _NUMWORDS:
            out.append(token)
            i += 1
            continue
        words = [key]
        j = i + 2  # skip the separator after this word
        while j < len(parts) and parts[j].lower().replace("ё", "е") in _NUMWORDS:
            words.append(parts[j].lower().replace("ё", "е"))
            j += 2
        unit = None
        if j < len(parts) and parts[j].lower().replace("ё", "е") in _UNIT_WORD:
            unit = _UNIT_WORD[parts[j].lower().replace("ё", "е")]
        if unit or len(words) >= 2:
            num = _ru_number(words)
            if num is not None:
                out.append(str(num) + (f" {unit}" if unit else ""))
                i = j + 1 if unit else max(j - 1, i + 1)
                continue
        out.append(token)
        i += 1
    return "".join(out)


def _label_base(label: str) -> str:
    w = label.lower().replace("ё", "е")
    for stem, base in (
        ("высот", "высота"), ("ширин", "ширина"), ("глубин", "глубина"), ("длин", "длина"),
        ("масс", "масса"), ("вес", "вес"), ("толщин", "толщина"), ("диаметр", "диаметр"),
        ("мощност", "мощность"), ("напряжен", "напряжение"), ("объем", "объем"),
        ("размер", "размер"), ("рост", "рост"),
    ):
        if w.startswith(stem):
            return base
    return w


def _color_base(word: str) -> str:
    w = word.lower().replace("ё", "е")
    for stem, base in _COLOR_STEMS:
        if w.startswith(stem):
            return base
    return w


def prepare_text(text: str) -> str:
    """Fold ё, fullwidth digits, translit and number-words. Safe to call twice."""
    if not text:
        return text
    text = text.translate(_FOLD).replace("ё", "е").replace("Ё", "Е")
    text = translit_if_latin(text)
    return _words_to_numbers(text)


_HTML_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.I | re.S)
_HTML_TAG = re.compile(r"</?[a-zA-Z!][^<>]*>")


def strip_html(text: str) -> str:
    """Replace HTML tags (and <script>/<style> bodies) by spaces of the same length.

    The result has exactly the same length as the input, so every span computed on it is also a valid
    span in the original text.
    """
    if not text or "<" not in text:
        return text
    blank = lambda m: " " * (m.end() - m.start())  # noqa: E731
    return _HTML_TAG.sub(blank, _HTML_BLOCK.sub(blank, text))


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


def na_dimensions(text: str) -> list[RawKV]:
    """«1080 на 650 на 450 мм» -> ширина, глубина, высота. Только для мебели."""
    out: list[RawKV] = []
    for m in _NA_DIMS.finditer(text):
        unit = canonicalize_unit(m.group("unit")) if m.group("unit") else None
        for name, val in zip(("Ширина", "Глубина", "Высота"), (m.group("a"), m.group("b"), m.group("c"))):
            out.append(RawKV(name=name, value=val.replace(",", "."), unit=unit))
    return out


def parse_free_text(text: str, domain: str | None = None) -> tuple[str, list[RawKV]]:
    text = re.sub(r"\s+", " ", prepare_text(text).strip())
    product = guess_product_name(text)
    found: list[RawKV] = []
    seen: set[tuple[str, str]] = set()

    def add(name: str, value: str, unit: str | None = None, bound: str | None = None) -> None:
        name = name.strip()
        value = value.strip(" .;")
        value = re.sub(r"^[−–](?=\d)", "-", value)  # minus sign variants: a negative value is never dropped
        if not name or not value:
            return
        key = (name.lower(), value.lower())
        if key in seen:
            return
        seen.add(key)
        m = re.match(
            r"^(?P<v>-?\d+(?:[.,]\d+)?)\s*(?P<u>мм|см|м|кг|г|гр|шт|мл|л|кВт|Вт|вт|В|А|т|тонна\w*|тонн\w*|%)$",
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
                bound=bound,
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

    if domain == "furniture":
        explicit_labels = set()
        for m in _NUM_UNIT.finditer(text):
            if re.match(r"\s*[хxX×*]\s*\d", text[m.end():]):
                continue
            explicit_labels.add(_label_base(m.group("label")))
        for kv in composite_dimensions(text) + na_dimensions(text):
            if kv.name.lower() not in explicit_labels:
                add(kv.name, kv.value, kv.unit)
        text_for_num = _NA_DIMS.sub(" ", _DIMS.sub(" ", text))
    else:
        text_for_num = text
    for m in _NUM_UNIT.finditer(text_for_num):
        if re.match(r"\s*[хxX×*]\s*\d", text_for_num[m.end():]):
            continue  # part of a composite value («17х19», «размер 1200х750»)
        add(_label_base(m.group("label")), m.group("value"), m.group("unit"),
            bound=re.sub(r"\s+", " ", m.group("op")).lower() if m.group("op") else None)
    for m in _NUM_UNIT_REV.finditer(text_for_num):
        before = text_for_num[:m.start()]
        if re.search(r"(?:размер\w*|рост\w*|высот\w*|ширин\w*|глубин\w*|длин\w*|масс\w*|вес\w*)\s+$", before, re.I):
            continue  # «размер 48-50 рост» is not «48-50» of роста
        add(_label_base(m.group("label")), m.group("value"))

    taken = {x.value for x in found}
    for m in _BARE_Q.finditer(text_for_num):
        if m.group("value") in taken:
            continue
        add("Частота вращения" if m.group("rpm") else "Напряжение", m.group("value"),
            "об/мин" if m.group("rpm") else "В")
        taken.add(m.group("value"))

    for m in _PERCENT.finditer(text):
        mat = (m.group("m1") or m.group("m2") or "").strip()
        add(f"Содержание {mat.lower()}", m.group("p1") or m.group("p2"), "%")

    for m in _COLOR.finditer(text):
        add("Цвет", _color_base(m.group("value")))
    for m in _COLOR_REV.finditer(text):
        add("Цвет", _color_base(m.group("value")))
    for m in _COLOR_BARE.finditer(text):
        add("Цвет", _color_base(m.group("value")))

    for m in _MATERIAL.finditer(text):
        add("Материал", m.group("value"))
    if _LAMINATE.search(text):
        add("Материал", "ЛДСП")
    for m in _BARE_MAT.finditer(text):
        add("Материал", m.group("value"))

    for token in ("ДСП", "МДФ", "ЛДСП"):
        if re.search(rf"\b{token}\b", text, re.I) and not any(
            x.name.lower() == "материал" for x in found
        ):
            add("Материал", token)

    return product, found
