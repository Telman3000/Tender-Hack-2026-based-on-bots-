"""Characteristic unification: KTRU (of the chosen code) -> portal frequency -> new property."""
from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from app.catalog import Catalog, KtruEntry, norm
from app.config import CHAR_ALIASES
from app.models import CharSource, Issue, ParsedCharacteristic
from app.parser import RawKV, canonicalize_name
from app.units import canon_unit, dimension, expected_dimension, to_number
from app.validate import check_value, is_numeric_spec, numeric_view, sanity_issues


_STOP = {"для", "или", "без", "при", "под", "над", "от", "из", "на", "по", "со"}


def _stem(w: str) -> str:
    return w[:6] if len(w) > 6 else w


# description word -> KTRU value word
_VALUE_SYNONYMS = {"ткань": "текстиль", "тканевая": "текстиль", "тканевый": "текстиль",
                   "кожзам": "искусственная", "экокожа": "экокожа", "аккумуляторная": "аккумуляторных",
                   "аккумуляторный": "аккумуляторных"}


def _text_stems(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for w in norm(text).split():
        if len(w) >= 3 and w not in _STOP:
            out.setdefault(_stem(w), w)
            syn = _VALUE_SYNONYMS.get(w)
            if syn:
                out.setdefault(_stem(syn), w)
    return out


# parts of an item: a value right after the part word belongs to that part only
_PARTS = ("каркас", "столешниц", "обивк", "спинк", "сиден", "фасад", "корпус", "подошв", "верх")


def _part_windows(text: str) -> dict[str, list[str]]:
    ws = norm(text).split()
    out: dict[str, list[str]] = {}
    for i, w in enumerate(ws):
        for p in _PARTS:
            if w.startswith(p):
                out.setdefault(p, []).extend(ws[i + 1:i + 4])
    return out


def _stems_for_spec(spec_key: str, text: str, windows: dict[str, list[str]]) -> dict[str, str]:
    spec_parts = [p for p in _PARTS if p in spec_key]
    own = [p for p in spec_parts if p in windows]
    if own:
        return _text_stems(" ".join(w for p in own for w in windows[p]))
    if "каркас" in spec_parts:
        return {}  # frame material only when stated explicitly («каркас ЛДСП»)
    foreign = {w for p, ws in windows.items() if p not in spec_parts for w in ws}
    return _text_stems(" ".join(w for w in norm(text).split() if w not in foreign))


_NAME_HEADS = ("цвет", "размер", "рост", "высот", "ширин", "глубин", "длин", "масс", "вес", "материал",
               "тип", "вид", "мощност", "напряжен", "обивк", "каркас", "столешниц", "конфигурац", "форм")


def _wstem(w: str) -> str:
    return w[:5] if len(w) > 5 else w


_ADJ_SUFFIXES = ("иевый", "иевая", "иевое", "иевые", "овый", "овая", "овое", "овые", "евый", "евая", "евое", "евые",
                 "янный", "янная", "янное", "янные", "яный", "ический", "ическая", "ическое", "ические",
                 "енный", "енная", "енное", "енные", "ный", "ная", "ное", "ные", "ой", "ый", "ий", "ая")


def _noun_stem(w: str) -> str:
    """Adjective -> noun stem: «алюминиевый» -> «алюмини», «деревянный» -> «дерев», «металлический» -> «металл»."""
    for suf in sorted(_ADJ_SUFFIXES, key=len, reverse=True):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: len(w) - len(suf)]
    return w


def _match_enum(sp, vals: list[str], rest: str):
    """Allowed value for the phrase: multi-word value inside the phrase, or adjective -> noun match."""
    for e in sp.enums:
        ne = norm(e)
        if ne and len(ne.split()) >= 2 and f" {ne} " in f" {rest} ":
            return e
    stems = [_noun_stem(w) for w in vals if len(w) >= 5]
    for e in sp.enums:
        ews = [w for w in norm(e).split() if len(w) >= 4]
        if ews and any(st != w and ew.startswith(st) for st, w in zip(stems, vals) for ew in ews):
            return e
    return None


def _phrase_words(text: str) -> list[tuple[str, int]]:
    """Normalised words with segment ids (segments are split by , ; | and line breaks)."""
    out = []
    for seg_id, seg in enumerate(re.split(r"[,;|\n]", text or "")):
        out.extend((w, seg_id) for w in norm(seg).split())
    return out


def _named_enum_values(best, text: str, used: set[str], domain, raw_heads: set[str] = frozenset(),
                       alternatives=(), known_values: dict[str, set[str]] | None = None):
    """Find «name value» for enum KTRU characteristics (full name, or a unique leading part of it).

    The value runs until the next characteristic name, number or separator. A value not in the allowed
    list is an error, unless the mapping is uncertain (shortened name / name inside a longer one /
    value allowed in another candidate code) — then it is a warning.
    """
    pw = _phrase_words(text)
    tw = [w for w, _ in pw]
    if not tw:
        return []
    specs = [(k, sp) for k, sp in best.specs.items()
             if sp.enums and k not in used and not _binary(sp)]
    names = {k: [w for w in norm(sp.name).split()] for k, sp in specs}
    found = []
    taken: set[int] = set()
    for k, sp in sorted(specs, key=lambda x: -len(names[x[0]])):
        nw = names[k]
        for L in range(len(nw), 0, -1):
            pref = nw[:L]
            if len(pref[0]) < 3:
                break
            if L < len(nw):
                # a shortened name only when the dropped words just repeat the product («Тип [молотка]»)
                prod = {_wstem(w) for w in norm(best.name).split()}
                if any(_wstem(w) not in prod for w in nw[L:] if w not in _STOP) or \
                        sum(1 for k2 in names if names[k2][:L] == pref) > 1:
                    continue
            if _wstem(pref[0]) in raw_heads:
                break
            hit = None
            for i in range(len(tw) - L):
                if all(_wstem(tw[i + j]) == _wstem(pref[j]) for j in range(L)) and i not in taken:
                    hit = i
                    break
            if hit is None:
                continue
            seg = pw[hit + L - 1][1]
            vals = []
            for w, sg in pw[hit + L:hit + L + 8]:
                if sg != seg or any(ch.isdigit() for ch in w) or any(w.startswith(h) for h in _NAME_HEADS):
                    break
                vals.append(w)
            while vals and vals[-1] in _STOP:
                vals.pop()
            if not vals:
                break
            taken.update(range(hit, hit + L + len(vals)))
            raw_val = " ".join(vals)
            r = check_value(sp, raw_val, None, domain)
            if not r.ok:
                alt = _match_enum(sp, vals, raw_val)
                if alt is not None:
                    r = check_value(sp, alt, None, domain)
            # uncertain mapping: name embedded in a longer phrase («вид материала наполнителя»), shortened name
            prev = tw[hit - 1] if hit > 0 else ""
            uncertain = L < len(nw) or (prev and (any(prev.startswith(h) for h in _NAME_HEADS) or
                                                  prev in ("материала", "вида")))
            other = None
            if not r.ok:
                for e in alternatives:
                    sp2 = e.specs.get(k)
                    if e.code != best.code and sp2 is not None and sp2.enums and check_value(sp2, raw_val, None, domain).ok:
                        other = e
                        break
            elsewhere = not r.ok and norm(raw_val) in (known_values or {}).get(sp.name.lower(), set())
            issue = r.issue
            if issue is not None and not r.ok and elsewhere and other is None and not uncertain:
                # the value exists in KTRU for this characteristic, just not for this code -> likely the code
                issue.severity = "warning"
                issue.message += " (значение есть в КТРУ для других позиций — проверьте выбор кода)"
            elif issue is not None and not r.ok and (uncertain or other is not None):
                issue.severity = "warning"
                issue.message += (f" (подходит для {other.code} «{other.name}»)" if other is not None
                                  else " (сопоставление названия неуверенное — проверьте)")
            span_txt = " ".join(tw[hit:hit + L + len(vals)])
            pc = ParsedCharacteristic(
                name=sp.name, raw_name=" ".join(tw[hit:hit + L]), canonical_name=sp.name,
                value=r.value if r.ok else raw_val, unit=None, source=CharSource.KTRU,
                required=sp.required, allowed=sp.allowed_enums(), user_input=span_txt,
                confidence=0.9 if r.ok else (0.4 if uncertain else 0.6),
                notes=f"Характеристика КТРУ {best.code}",
            )
            found.append((pc, issue))
            break
    return found


# word-level synonyms of characteristic names (the KTRU / portal wording wins)
_NAME_WORD_SYN = {"вес": "масса", "веса": "массы", "весом": "массой", "объём": "объем", "объёма": "объема",
                  "расцветка": "цвет", "окраска": "цвет", "колер": "цвет", "габарит": "размер",
                  "напряжения": "напряжения", "питания": "питания"}
_HEADS_FIRST = ("цвет", "размер", "высот", "ширин", "глубин", "длин", "масс", "материал", "тип", "вид",
                "мощност", "напряжен", "объем", "толщин", "диаметр", "количеств", "форм", "назначен")


def uniform_name(name: str) -> str:
    """One formulation for a property name: case, ё, synonyms, head word first («корпуса цвет» -> «Цвет корпуса»)."""
    ws = [w for w in re.split(r"[\s_]+", (name or "").strip().lower().replace("ё", "е")) if w]
    ws = [_NAME_WORD_SYN.get(w, w) for w in ws]
    if len(ws) > 1 and not any(ws[0].startswith(h) for h in _HEADS_FIRST):
        for i, w in enumerate(ws[1:], 1):
            if any(w.startswith(h) for h in _HEADS_FIRST):
                ws = [w] + ws[:i] + ws[i + 1:]
                break
    out = " ".join(ws).strip(" .,:;-")
    return out[:1].upper() + out[1:] if out else (name or "")


# dimensions that belong to specific item types (powered tools...); a mass or a length fits anything
_SPECIFIC_DIMS = {"power", "voltage", "current", "charge", "rpm", "freq", "torque"}


def _group_profile(cat: Catalog, best: KtruEntry) -> tuple[set[str], set[str]]:
    """Dimensions and characteristic name stems used by KTRU positions of the chosen code's OKPD2 class.

    Positions of the same OKPD2 class (first two levels, 28.24 = power tools) with the same head noun count,
    so a power rating is normal for a 28.24.x jackhammer even if its exact group does not list it; power-tool
    and machine names (see _POWERED) never get such a warning.
    """
    cache = cat.__dict__.setdefault("_group_profile", {})
    head = (best.name_norm.split() or [""])[0][:5]
    key = ((best.okpd2 or best.code)[:5], head)
    if key not in cache:
        dims: set[str] = set()
        stems: set[str] = set()
        for e in cat.entries:
            if (e.okpd2 or e.code)[:5] != key[0] or (e.name_norm.split() or [""])[0][:5] != head:
                continue
            for sp in e.specs.values():
                d = dimension(canon_unit(sp.unit)) or expected_dimension(sp.name)
                if d:
                    dims.add(d)
                stems.update(_wstem(w) for w in norm(sp.name).split() if len(w) >= 4)
        cache[key] = (dims, stems)
    return cache[key]


_POWERED = ("аккумулятор", "электр", "отбойн", "пневмат", "сетев", "беспровод", "бесщеточ", "перфорат",
            "гайковерт", "болгарк", "лобзик", "дрел", "шуруповерт", "шлифмашин", "пила", "пилы", "рубан",
            "фрезер", "молоток отбойн", "компрессор", "генератор", "станок", "машин", "триммер", "газонокос",
            "мойк", "пылесос", "фен", "паяльн", "сварочн", "насос")


def _powered(text: str) -> bool:
    t = norm(text)
    return any(f" {st}" in f" {t}" for st in _POWERED)


def suspicious_issue(cat: Catalog, best: KtruEntry | None, name: str, value: str, unit: str | None,
                     text: str = "") -> Issue | None:
    """«мощность гаечного ключа 100»: a quantity whose dimension no KTRU position of this item type has."""
    if best is None or not value:
        return None
    dim = dimension(canon_unit(unit)) or expected_dimension(name)
    if dim not in _SPECIFIC_DIMS:
        return None
    if _powered(best.name) or _powered(text):
        return None  # power tools / machines: power, voltage, rpm... are normal
    dims, stems = _group_profile(cat, best)
    if dim in dims or any(_wstem(w) in stems for w in norm(name).split() if len(w) >= 4):
        return None
    shown = f"{value} {unit}".strip() if unit else value
    return Issue.make(
        "mismatch", field=uniform_name(name), value=shown, severity="warning",
        expected="характеристика, применимая к «" + best.name + "»",
        message=f"Характеристика не подходит к типу товара: «{uniform_name(name)} {shown}» "
                f"не встречается у позиций КТРУ «{best.name}» — проверьте ввод",
    )


def _binary(sp) -> bool:
    vals = {norm(e) for e in sp.enums}
    return bool(vals) and vals <= {"да", "нет"}


def _enum_from_text(spec, stems: dict[str, str]) -> tuple[str, str] | None:
    """Pick the allowed KTRU value whose significant words occur in the description."""
    best, best_sc, tie = None, 0.0, False
    for e in dict.fromkeys(spec.enums):
        ws = [w for w in norm(e).split() if len(w) >= 3 and w not in _STOP]
        if not ws:
            continue
        hit = [stems[_stem(w)] for w in ws if _stem(w) in stems]
        if not hit:
            continue
        sc = len(hit) / len(ws) + 0.01 * len(hit)
        if sc > best_sc + 1e-9:
            best, best_sc, tie = (e, " ".join(hit)), sc, False
        elif abs(sc - best_sc) <= 1e-9:
            tie = True
    if best and not tie and best_sc >= 0.5:
        return best
    return None


def unify_characteristics(
    cat: Catalog,
    raw: list[RawKV],
    domain: str | None,
    best: KtruEntry | None,
    user_rows: set[str] | None = None,
    text: str = "",
    corrections: list | None = None,
    alternatives=(),
) -> tuple[list[ParsedCharacteristic], list[Issue]]:
    issues: list[Issue] = []
    out: list[ParsedCharacteristic] = []
    portal = cat.portal_names.get(domain) or cat.portal_names.get(None) or []
    used: set[str] = set()

    for item in raw:
        user_input = f"{item.name} {item.value}{' ' + item.unit if item.unit else ''}".strip()
        value = (item.value or "").strip()
        unit = canon_unit(item.unit) or item.unit
        spec = cat.find_spec(best, item.name) if best else None
        if spec is None and best is not None:
            # synonyms: «вес» and «масса» land on the same KTRU characteristic («Масса молотка»)
            for alias in dict.fromkeys(filter(None, (CHAR_ALIASES.get(item.name.lower().strip()),
                                                     uniform_name(item.name)))):
                spec = cat.find_spec(best, alias)
                if spec is not None:
                    break
        if value and not unit and to_number(value) is not None and (
                expected_dimension(spec.name if spec else item.name) == "length"
                or (spec is not None and dimension(canon_unit(spec.unit)) == "length")):
            num = to_number(value)
            unit = "м" if (num < 10 and num != int(num)) else "мм"
            item = RawKV(name=item.name, value=item.value, unit=unit)
            issues.append(Issue.make(
                "unit", field=spec.name if spec else item.name, value=value, expected=unit,
                suggestions=[f"{value} {unit}"], severity="warning",
                message=f"«{spec.name if spec else item.name}»: единица не указана — принято {value} {unit}",
            ))
        pc = ParsedCharacteristic(
            name=item.name, raw_name=item.name, canonical_name=item.name,
            value=value, unit=unit, user_input=user_input,
        )
        if spec is not None:
            pc.name = pc.canonical_name = spec.name
            pc.source = CharSource.KTRU
            pc.required = spec.required
            pc.allowed = spec.allowed_enums()
            if is_numeric_spec(spec):
                pc.min, pc.max, nu = numeric_view(spec, domain)
                pc.unit = nu or pc.unit
            pc.confidence = 0.95
            pc.notes = f"Характеристика КТРУ {best.code}"
            if spec.is_numeric and spec.unit:
                pc.unit = canon_unit(spec.unit) or spec.unit
            if value:
                r = check_value(spec, value, item.unit, domain)
                if r.issue:
                    issues.append(r.issue)
                if r.ok:
                    if corrections is not None and r.converted and item.unit:
                        corrections.append(("unit", spec.name, f"{value} {item.unit}", f"{r.value} {r.unit}"))
                    pc.value, pc.unit = r.value, (r.unit or pc.unit)
            used.add(spec.name.lower())
        else:
            canon = CHAR_ALIASES.get(item.name.lower().strip())
            sus = suspicious_issue(cat, best, item.name, value, unit, text)
            match = None
            if portal:
                match = process.extractOne(canon or item.name, portal, scorer=fuzz.WRatio, score_cutoff=85)
            if match:
                pc.name = pc.canonical_name = match[0]
                pc.source = CharSource.PORTAL
                pc.confidence = match[1] / 100.0
                n = cat.portal_freq.get((domain, match[0]), 0)
                pc.notes = f"Характеристика портала (встречается в {n} категориях)"
            elif canon:
                pc.name = pc.canonical_name = canon
                pc.source = CharSource.PORTAL
                pc.confidence = 0.8
                pc.notes = "Унифицировано по словарю"
            else:
                pc.name = pc.canonical_name = uniform_name(canonicalize_name(item.name))
                pc.source = CharSource.NEW
                pc.confidence = 0.55
                pc.notes = "Новое свойство (нет в КТРУ и выгрузках портала)"
                if sus is None:
                    issues.append(Issue.make(
                        "new_property", field=pc.name, value=value, severity="warning",
                        message=f"Характеристика «{item.name}» не найдена в КТРУ и выгрузках — заведена как новая",
                    ))
            if sus is not None:
                pc.suspicious = True
                pc.confidence = min(pc.confidence, 0.3)
                pc.notes = "Подозрительная характеристика: не подходит к типу товара"
                sus.field = pc.name
                issues.append(sus)
        if value:
            have = {(i.type, i.field) for i in issues}
            ktru_sized = spec is not None and (spec.enums or spec.ranges or spec.numbers)
            for i in sanity_issues(item.name, value, item.unit, domain, text):
                if ktru_sized and item.name.lower().startswith("размер"):
                    continue  # KTRU allowed values win over the common-sense size table
                if (i.type, i.field) not in have and not (spec and spec.is_numeric and i.type == "unit"):
                    issues.append(i)
        out.append(pc)

    # «<KTRU characteristic name> <value>» in free text: never drop the value silently
    if best:
        raw_heads = {_wstem(norm(r.name).split()[0]) for r in raw if norm(r.name)}
        same_okpd = [e for e in cat.entries if e.code[:12] == best.code[:12] and e.code != best.code][:300]
        for pc, issue in _named_enum_values(best, text, used, domain, raw_heads, list(alternatives) + same_okpd,
                                            cat.enum_values_by_name()):
            out.append(pc)
            used.add(pc.name.lower())
            if issue:
                issues.append(issue)

    # required KTRU characteristics not provided
    if best:
        windows = _part_windows(text)
        for k, sp in best.specs.items():
            if not sp.required or k in used:
                continue
            found = _enum_from_text(sp, _stems_for_spec(k, text, windows)) if sp.enums else None
            if found:
                value, words = found
                out.append(ParsedCharacteristic(
                    name=sp.name, raw_name=sp.name, canonical_name=sp.name, value=value,
                    unit=None, source=CharSource.KTRU, required=True, allowed=sp.allowed_enums(),
                    user_input=words, confidence=0.8,
                    notes="Значение найдено в описании по допустимым значениям КТРУ",
                ))
                used.add(k)
                continue
            lo, hi, nu = numeric_view(sp, domain) if is_numeric_spec(sp) else (None, None, canon_unit(sp.unit) or sp.unit)
            out.append(ParsedCharacteristic(
                name=sp.name, raw_name="", canonical_name=sp.name, value="",
                unit=nu, source=CharSource.KTRU, required=True,
                allowed=sp.allowed_enums(), min=lo, max=hi, confidence=0.0,
                notes="Обязательная характеристика КТРУ — не заполнена",
            ))
            issues.append(Issue.make(
                "missing", field=sp.name, severity="warning",
                expected=", ".join((sp.allowed_enums() or [])[:5]) or None,
                suggestions=(sp.allowed_enums() or [])[:3],
                message=f"Не заполнена обязательная характеристика КТРУ «{sp.name}»",
            ))
    # optional KTRU characteristics of the chosen code that are not filled: listed too (allowed values, range)
    if best:
        for k, sp in best.specs.items():
            if sp.required or k in used or any(c.name.lower() == k for c in out):
                continue
            lo, hi, nu = numeric_view(sp, domain) if is_numeric_spec(sp) else (None, None, canon_unit(sp.unit) or sp.unit)
            out.append(ParsedCharacteristic(
                name=sp.name, raw_name="", canonical_name=sp.name, value="",
                unit=nu, source=CharSource.KTRU, required=False,
                allowed=sp.allowed_enums(), min=lo, max=hi, confidence=0.0,
                notes="Необязательная характеристика КТРУ — не заполнена",
            ))
    # a text-parsed portal row whose value already went into a KTRU characteristic is a duplicate
    ktru_vals = {norm(c.value) for c in out if c.source == CharSource.KTRU and c.value}
    keep_user = {u.lower() for u in (user_rows or set())}
    out = [c for c in out if not (c.source != CharSource.KTRU and c.value and norm(c.value) in ktru_vals
                                  and (c.raw_name or c.name).lower() not in keep_user)]
    return order_characteristics(out), issues


_SOURCE_RANK = {CharSource.KTRU: 0, CharSource.PORTAL: 1, CharSource.NEW: 2, CharSource.USER: 2}


def order_characteristics(chars: list[ParsedCharacteristic]) -> list[ParsedCharacteristic]:
    """KTRU -> portal -> new (suspicious last); inside KTRU: filled, then empty required, then empty optional."""
    return sorted(chars, key=lambda c: (_SOURCE_RANK.get(c.source, 2), c.suspicious,
                                        0 if c.value else (1 if c.required else 2)))
