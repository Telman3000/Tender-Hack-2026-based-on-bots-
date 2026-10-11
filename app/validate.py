"""Value validation against KTRU: allowed lists, numeric ranges, units (OKEI)."""
from __future__ import annotations

import re

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.catalog import CharSpec, norm
from app.models import Issue
from app.units import UNITS as _UNITS_KNOWN
from app.units import canon_unit, convert, dimension, expected_dimension, fmt, guess_unit, to_number

# common-sense upper bounds when KTRU gives no range: domain -> dim -> (unit, max, label)
# domain -> dimension -> (unit, max, what[, min]); min applies to main dimensions only
_LIMITS = {
    "furniture": {"length": ("м", 5, "мебели", 0.1), "mass": ("кг", 500, "мебели", 0.1)},
    "tools": {"length": ("м", 3, "ручного инструмента", 0.01), "mass": ("кг", 100, "инструмента", 0.005),
              "voltage": ("В", 1000, "инструмента", 1), "power": ("Вт", 10000, "инструмента", 1)},
    "clothing": {"length": ("м", 3, "одежды"), "mass": ("кг", 20, "одежды", 0.005)},
}
_MAIN_DIMS = {"высота", "ширина", "глубина", "длина", "габаритная высота", "габаритная ширина",
              "габаритная глубина", "габаритная длина"}
# item type (word stems in the description) -> typical size range; first match wins
_SIZE_RANGES = (
    (("перчат", "рукавиц", "краг"), 5, 13, "размера перчаток"),
    (("шапк", "кепк", "берет", "бейсболк", "панам", "каск", "шлем", "головн"), 46, 66, "размера головного убора"),
    (("обув", "ботин", "сапог", "туфл", "кроссов", "кед", "тапоч", "сандал", "галош"), 15, 50, "размера обуви"),
)


def size_range(text: str, domain: str | None) -> tuple[float, float, str] | None:
    words = re.findall(r"[а-яё]+", (text or "").lower())
    for stems, lo, hi, what in _SIZE_RANGES:
        if any(w.startswith(st) for w in words for st in stems):
            return lo, hi, what
    if domain == "clothing":
        return 18, 80, "российского размера одежды"
    return None


_DIM_HINT = {"length": ["мм", "см"], "mass": ["кг", "г"], "volume": ["л", "мл"], "power": ["Вт"]}


def _plausible_units(num: float, unit: str | None, dim: str | None, base_u: str, hi: float) -> list[str]:
    """Other units of the same dimension whose converted value stays inside the cap."""
    out = []
    for alt in _DIM_HINT.get(dim or "", []):
        if alt == unit:
            continue
        conv = convert(num, alt, base_u)
        if conv is not None and 0 < conv <= hi:
            out.append(f"{fmt(num) if isinstance(num, float) else num} {alt}")
    return out[:2]


@dataclass
class CheckResult:
    ok: bool
    value: str
    unit: str | None
    issue: Issue | None = None
    converted: bool = False


def _in_range(x: float, lo, hi, lo_op, hi_op) -> bool:
    eps = 1e-9
    if lo is not None:
        if lo_op and lo_op.lower().startswith("greater") and "equal" not in lo_op.lower():
            if not x > lo + eps:
                return False
        elif x < lo - eps:
            return False
    if hi is not None:
        if hi_op and hi_op.lower().startswith("less") and "equal" not in hi_op.lower():
            if not x < hi - eps:
                return False
        elif x > hi + eps:
            return False
    return True


def _range_text(spec: CharSpec) -> str:
    parts = []
    for lo, hi, lo_op, hi_op in spec.ranges[:3]:
        a = ("> " if lo_op and "equal" not in lo_op.lower() else "≥ ") + fmt(lo) if lo is not None else ""
        b = ("< " if hi_op and "equal" not in hi_op.lower() else "≤ ") + fmt(hi) if hi is not None else ""
        parts.append(" и ".join(p for p in (a, b) if p))
    if spec.numbers:
        parts.append(", ".join(fmt(n) for n in sorted(set(spec.numbers))[:8]))
    u = canon_unit(spec.unit) or spec.unit or ""
    return "; ".join(parts) + (f" {u}" if u else "")


def check_value(
    spec: CharSpec,
    value: str,
    unit: str | None,
    domain: str | None = None,
    emit: bool = True,
) -> CheckResult:
    """Validate one user value against a KTRU characteristic spec."""
    field = spec.name
    if spec.is_numeric:
        num = to_number(value)
        target = canon_unit(spec.unit) or spec.unit
        if num is None:
            return CheckResult(
                False, value, unit,
                Issue.make(
                    "mismatch", field=field, value=value, expected=_range_text(spec),
                    message=f"«{field}»: ожидается число, получено «{value}»",
                    severity="error",
                ) if emit else None,
            )
        u = canon_unit(unit)
        guessed = False
        if not u and target:
            lows = [r[0] for r in spec.ranges if r[0] is not None] + spec.numbers
            highs = [r[1] for r in spec.ranges if r[1] is not None] + spec.numbers
            u = guess_unit(num, field, target, min(lows) if lows else None,
                           max(highs) if highs else None, domain)
            guessed = True
        x = num
        converted = False
        if target and u:
            if dimension(u) and dimension(target) and dimension(u) != dimension(target):
                return CheckResult(
                    False, value, u,
                    Issue.make(
                        "unit", field=field, value=f"{value} {u}", expected=target,
                        message=f"«{field}»: единица «{u}» несовместима с единицей КТРУ «{target}»",
                        suggestions=[f"{value} {target}"], severity="error",
                    ) if emit else None,
                )
            conv = convert(num, u, target)
            if conv is not None:
                converted = u != target
                x = conv
        ok = any(_in_range(x, *r) for r in spec.ranges) or any(abs(x - n) < 1e-6 for n in spec.numbers)
        out_val, out_unit = (fmt(x), target) if target else (value, u)
        if not ok:
            sugg = []
            if spec.numbers:
                sugg = [fmt(n) + (f" {target}" if target else "")
                        for n in sorted(set(spec.numbers), key=lambda n: abs(n - x))[:3]]
            return CheckResult(
                False, out_val, out_unit,
                Issue.make(
                    "out_of_range" if spec.ranges else "not_allowed",
                    field=field, value=f"{value} {u or ''}".strip(), expected=_range_text(spec),
                    suggestions=sugg,
                    message=(
                        f"«{field}» = {value} {u or ''}".rstrip()
                        + (f" (= {fmt(x)} {target})" if converted else "")
                        + f" вне допустимых значений КТРУ: {_range_text(spec)}"
                    ),
                    severity="error",
                ) if emit else None,
                converted,
            )
        issue = None
        if guessed and emit and u:
            issue = Issue.make(
                "unit", field=field, value=value, expected=target,
                message=f"«{field}»: единица не указана — принято {value} {u}"
                + (f" = {fmt(x)} {target}" if converted else ""),
                suggestions=[f"{value} {u}"], severity="warning",
            )
        return CheckResult(True, out_val, out_unit, issue, converted)

    if spec.enums:
        nv = norm(value)
        choices = {norm(e): e for e in spec.enums}
        if nv in choices:
            return CheckResult(True, choices[nv], unit)
        # word-level containment ("ЛДСП" in "Ламинированная ДСП (ЛДСП)")
        for ne, e in choices.items():
            if nv and (f" {nv} " in f" {ne} " or f" {ne} " in f" {nv} "):
                return CheckResult(True, e, unit)
        m = process.extract(nv, list(choices.keys()), scorer=fuzz.WRatio, limit=3)
        if m and m[0][1] >= 92:
            return CheckResult(True, choices[m[0][0]], unit, Issue.make(
                "typo", field=field, value=value, expected=choices[m[0][0]],
                suggestions=[choices[m[0][0]]], severity="warning",
                message=f"«{field}»: «{value}» исправлено на «{choices[m[0][0]]}»",
            ) if emit else None)
        sugg = [choices[x[0]] for x in m]
        return CheckResult(
            False, value, unit,
            Issue.make(
                "not_allowed", field=field, value=value,
                expected=", ".join(list(dict.fromkeys(spec.enums))[:8]),
                suggestions=sugg, severity="error",
                message=f"«{field}» = «{value}» — такого значения нет в КТРУ для этой позиции",
            ) if emit else None,
        )
    return CheckResult(True, value, unit)


def sanity_issues(name: str, value: str, unit: str | None, domain: str | None, text: str = "") -> list[Issue]:
    """Common-sense checks when KTRU has no constraint (furniture/tool sizes)."""
    out: list[Issue] = []
    num = to_number(value)
    if num is None:
        return out
    u = canon_unit(unit)
    low = name.lower()
    exp = expected_dimension(name)
    if u and exp and dimension(u) and dimension(u) != exp:
        out.append(Issue.make(
            "unit", field=name, value=f"{value} {u}", expected=exp,
            message=f"«{name}» не может измеряться в «{u}»",
            suggestions=[f"{value} {x}" for x in _DIM_HINT.get(exp, [])], severity="error"))
        return out
    if u == "%" and not 0 <= num <= 100:
        out.append(Issue.make(
            "mismatch", field=name, value=f"{value} %", expected="0–100 %",
            message=f"«{name}» = {value}% — доля не может превышать 100%", severity="error"))
    if num <= 0 and any(k in low for k in ("высот", "ширин", "глубин", "длин", "масс", "вес", "мощност")):
        out.append(Issue.make("mismatch", field=name, value=value, expected="> 0",
                              message=f"«{name}» должно быть положительным", severity="error"))
    if not u and low.startswith("размер"):
        rng = size_range(text, domain)
        if rng:
            lo, hi, what = rng
            nums = [to_number(x) for x in re.split(r"[-–/]", value)]
            if any(n is not None and not lo <= n <= hi for n in nums):
                out.append(Issue.make(
                    "mismatch", field=name, value=value, expected=f"{lo}–{hi}",
                    message=f"«{name}» = {value} вне типичного диапазона {what} ({lo}–{hi})",
                    severity="error"))
    if domain == "clothing" and not u and low.startswith("рост") and not 50 <= num <= 220:
        out.append(Issue.make(
            "mismatch", field=name, value=value, expected="50–220",
            message=f"«{name}» = {value} вне типичного диапазона роста, см (50–220)", severity="error"))
    limits = _LIMITS.get(domain or "", {})
    dim = dimension(u) if u else None
    if dim in limits:
        base_u, hi, what = limits[dim][:3]
        lo = limits[dim][3] if len(limits[dim]) > 3 else None
        conv = convert(num, u, base_u)
        main_dim = dim != "length" or low.strip() in _MAIN_DIMS
        if conv is not None and lo is not None and main_dim and 0 < conv < lo:
            out.append(Issue.make(
                "mismatch", field=name, value=f"{value} {u}", expected=f"от {fmt(lo)} {base_u}",
                message=f"«{name}» = {value} {u} нереалистично мало для {what} (меньше {fmt(lo)} {base_u})",
                suggestions=_plausible_units(num, u, dim, base_u, hi), severity="error"))
        if conv is not None and conv > hi:
            out.append(Issue.make(
                "mismatch", field=name, value=f"{value} {u}", expected=f"до {fmt(hi)} {base_u}",
                message=f"«{name}» = {value} {u} нереалистично для {what} (больше {fmt(hi)} {base_u})",
                suggestions=_plausible_units(num, u, dim, base_u, hi), severity="error"))
    return out


_BASE_UNIT = {"length": "мм", "mass": "кг", "volume": "л", "power": "Вт", "voltage": "В", "charge": "А·ч"}
_GENERIC_MAX = {"length": ("м", 10), "mass": ("кг", 1000), "volume": ("л", 1000), "power": ("Вт", 100000),
                "voltage": ("В", 1000), "charge": ("А·ч", 100), "percent": ("%", 100), "count": ("шт", 1000),
                "rpm": ("об/мин", 100000), "torque": ("Н·м", 10000), "freq": ("Гц", 100000),
                "area": ("м2", 1000), "density": ("г/м2", 2000), "db": ("дБ", 200)}


def is_numeric_spec(spec: CharSpec) -> bool:
    return spec.is_numeric or (not spec.enums and bool(spec.unit))


def numeric_view(spec: CharSpec, domain: str | None) -> tuple[float | None, float | None, str | None]:
    """min/max/unit for a numeric KTRU characteristic: KTRU range, else common-sense limits."""
    unit = canon_unit(spec.unit) or spec.unit
    if not unit:
        m = re.search(r"\(([^()]+)\)\s*$", spec.name)  # «Максимальный крутящий момент (Нм)»
        unit = canon_unit(m.group(1)) if m and canon_unit(m.group(1)) in _UNITS_KNOWN else None
    if not unit:
        low = spec.name.lower()
        dim = expected_dimension(spec.name)
        if dim:
            unit = _BASE_UNIT.get(dim)
        elif any(k in low for k in ("количеств", "число", "секци", "ящик", "полок", "мест")):
            unit = "шт"
        else:
            unit = "ед."  # dimensionless KTRU number (code/grade)
    lo, hi = spec.bounds() if spec.is_numeric else (None, None)
    dim = dimension(unit)
    if hi is None and dim:
        lim = _LIMITS.get(domain or "", {}).get(dim)
        base_u, cap = (lim[0], lim[1]) if lim else _GENERIC_MAX.get(dim, (None, None))
        if base_u:
            hi = convert(cap, base_u, unit)
    if lo is None and (hi is not None or dim):
        lo = 0.0
    return lo, hi, unit
