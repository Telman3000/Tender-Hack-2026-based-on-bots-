"""Units of measure: aliases, OKEI names, conversion within a dimension."""
from __future__ import annotations

import re

# canonical short unit -> (dimension, factor to base unit)
UNITS: dict[str, tuple[str, float]] = {
    "мм": ("length", 0.001),
    "см": ("length", 0.01),
    "дм": ("length", 0.1),
    "м": ("length", 1.0),
    "км": ("length", 1000.0),
    "мг": ("mass", 1e-6),
    "г": ("mass", 0.001),
    "кг": ("mass", 1.0),
    "т": ("mass", 1000.0),
    "мл": ("volume", 0.001),
    "л": ("volume", 1.0),
    "м3": ("volume", 1000.0),
    "мм2": ("area", 1e-6),
    "см2": ("area", 1e-4),
    "м2": ("area", 1.0),
    "Вт": ("power", 1.0),
    "кВт": ("power", 1000.0),
    "В": ("voltage", 1.0),
    "А": ("current", 1.0),
    "мА·ч": ("charge", 0.001),
    "А·ч": ("charge", 1.0),
    "об/мин": ("rpm", 1.0),
    "Н·м": ("torque", 1.0),
    "Гц": ("freq", 1.0),
    "%": ("percent", 1.0),
    "шт": ("count", 1.0),
    "г/м2": ("density", 1.0),
    "дБ": ("db", 1.0),
}

_ALIASES = {
    "mm": "мм", "миллиметр": "мм", "миллиметров": "мм",
    "cm": "см", "сантиметр": "см", "сантиметров": "см",
    "дециметр": "дм",
    "m": "м", "метр": "м", "метров": "м", "метра": "м",
    "километр": "км",
    "миллиграмм": "мг",
    "g": "г", "гр": "г", "грамм": "г", "граммов": "г",
    "kg": "кг", "килограмм": "кг", "килограммов": "кг",
    "тонна": "т",
    "ml": "мл", "миллилитр": "мл", "кубический сантиметр": "мл", "см3": "мл",
    "l": "л", "литр": "л", "литров": "л", "литр; кубический дециметр": "л", "дм3": "л",
    "кубический метр": "м3", "м³": "м3",
    "квадратный метр": "м2", "м²": "м2", "квадратный сантиметр": "см2", "квадратный миллиметр": "мм2",
    "w": "Вт", "вт": "Вт", "ватт": "Вт",
    "квт": "кВт", "киловатт": "кВт",
    "v": "В", "в": "В", "вольт": "В",
    "a": "А", "а": "А", "ампер": "А",
    "ач": "А·ч", "а*ч": "А·ч", "а·ч": "А·ч", "ампер-час": "А·ч", "ah": "А·ч",
    "мач": "мА·ч", "ма*ч": "мА·ч", "мa·ч": "мА·ч", "ма·ч": "мА·ч", "mah": "мА·ч",
    "миллиампер-час": "мА·ч",
    "об/мин": "об/мин", "оборот в минуту": "об/мин", "rpm": "об/мин",
    "нм": "Н·м", "н*м": "Н·м", "н·м": "Н·м", "ньютон-метр": "Н·м",
    "гц": "Гц", "герц": "Гц",
    "процент": "%", "%": "%",
    "шт": "шт", "штука": "шт", "штук": "шт",
    "грамм на квадратный метр": "г/м2", "г/м2": "г/м2", "г/м²": "г/м2",
    "децибел": "дБ", "дб": "дБ",
}


def canon_unit(unit: str | None) -> str | None:
    """Map user unit or OKEI name to a short canonical unit (None if unknown/empty)."""
    if not unit:
        return None
    u = unit.strip()
    if u in UNITS:
        return u
    low = u.lower().replace("ё", "е").rstrip(".")
    if low in _ALIASES:
        return _ALIASES[low]
    for k in UNITS:
        if k.lower() == low:
            return k
    # OKEI names like "Метр" / "Сантиметр"
    first = low.split(";")[0].strip()
    return _ALIASES.get(first)


def dimension(unit: str | None) -> str | None:
    cu = canon_unit(unit)
    return UNITS[cu][0] if cu in UNITS else None


def convert(value: float, src: str | None, dst: str | None) -> float | None:
    s, d = canon_unit(src), canon_unit(dst)
    if not s or not d or s not in UNITS or d not in UNITS:
        return None
    if UNITS[s][0] != UNITS[d][0]:
        return None
    return value * UNITS[s][1] / UNITS[d][1]


def to_number(value: str | None) -> float | None:
    if value is None:
        return None
    m = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)\s*", str(value))
    return float(m.group(1).replace(",", ".")) if m else None


def fmt(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".")


# Typical units for bare numbers, by characteristic keyword (used to guess)
_DEFAULT_DIM = {
    "высот": "length", "ширин": "length", "глубин": "length", "длин": "length",
    "толщин": "length", "диаметр": "length",
    "масс": "mass", "вес": "mass",
    "объем": "volume", "объём": "volume", "вместимост": "volume",
    "мощност": "power", "напряжен": "voltage", "емкост": "charge", "ёмкост": "charge",
}

_DIM_CANDIDATES = {
    "length": ["мм", "см", "м"],
    "mass": ["г", "кг"],
    "volume": ["мл", "л"],
    "power": ["Вт", "кВт"],
    "voltage": ["В"],
    "charge": ["мА·ч", "А·ч"],
}


def expected_dimension(char_name: str) -> str | None:
    low = char_name.lower()
    for k, d in _DEFAULT_DIM.items():
        if k in low:
            return d
    return None


def guess_unit(
    num: float,
    char_name: str,
    target_unit: str | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
    domain: str | None = None,
) -> str | None:
    """Pick the most plausible unit for a bare number.

    With a known KTRU range in target_unit: first candidate unit whose converted value
    lands inside the range. Otherwise heuristics by magnitude (furniture sizes).
    """
    dim = dimension(target_unit) or expected_dimension(char_name)
    if not dim or dim not in _DIM_CANDIDATES:
        return canon_unit(target_unit)
    cands = _DIM_CANDIDATES[dim]
    if target_unit and (vmin is not None or vmax is not None):
        for u in [canon_unit(target_unit)] + [c for c in cands if c != canon_unit(target_unit)]:
            conv = convert(num, u, target_unit)
            if conv is None:
                continue
            if (vmin is None or conv >= vmin) and (vmax is None or conv <= vmax):
                return u
    if dim == "length":
        if num < 10 and num != int(num):
            return "м"
        if num < 10:
            return "м" if domain == "furniture" else "см"
        return "мм" if num >= 300 else "см"
    if dim == "mass":
        return "кг" if num < 100 else "г"
    if dim == "volume":
        return "л" if num < 100 else "мл"
    return canon_unit(target_unit) or cands[0]
