"""Characteristic unification: KTRU (of the chosen code) -> portal frequency -> new property."""
from __future__ import annotations

from rapidfuzz import fuzz, process

from app import morph
from app.catalog import Catalog, CharSpec, KtruEntry, norm
from app.config import CHAR_ALIASES
from app.models import CharSource, Issue, ParsedCharacteristic
from app.parser import RawKV, canonicalize_name
from app.units import canon_unit
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


def _enum_from_text(spec, stems: dict[str, str], full: bool = False) -> tuple[str, str] | None:
    """Pick the allowed KTRU value whose significant words occur in the description."""
    best, best_sc, tie = None, 0.0, False
    for e in dict.fromkeys(spec.enums):
        ws = [w for w in norm(e).split() if len(w) >= 3 and w not in _STOP]
        if not ws:
            continue
        hit = [stems[_stem(w)] for w in ws if _stem(w) in stems]
        if not hit or (full and len(hit) < len(ws)):
            continue
        sc = len(hit) / len(ws) + 0.01 * len(hit)
        if sc > best_sc + 1e-9:
            best, best_sc, tie = (e, " ".join(hit)), sc, False
        elif abs(sc - best_sc) <= 1e-9:
            tie = True
    if best and not tie and best_sc >= 0.5:
        return best
    return None


def _material_issue(best: KtruEntry, name: str, value: str) -> Issue | None:
    known = best.materials()
    if known is None:
        return None
    r = check_value(known, value, None)
    if r.ok:
        return None
    where = ", ".join(f"«{sp.name}»" for sp in best.material_specs()[:3])
    return Issue.make(
        "not_allowed", field=name, value=value, expected=", ".join(known.enums[:8]),
        suggestions=r.issue.suggestions if r.issue else [], severity="warning",
        message=f"«{value}» нет среди допустимых значений КТРУ {best.code} для {where} — "
                f"проверьте, к какой характеристике относится материал",
    )


def _variant_values(key: str, spec: CharSpec, variants: list[KtruEntry]) -> list[str] | None:
    values = list(spec.enums)
    for e in variants:
        other = e.specs.get(key)
        if other is not None:
            values.extend(other.enums)
    return list(dict.fromkeys(values))[:50] or None


def unify_characteristics(
    cat: Catalog,
    raw: list[RawKV],
    domain: str | None,
    best: KtruEntry | None,
    user_rows: set[str] | None = None,
    text: str = "",
    variants: list[KtruEntry] | None = None,
) -> tuple[list[ParsedCharacteristic], list[Issue]]:
    issues: list[Issue] = []
    out: list[ParsedCharacteristic] = []
    portal = cat.portal_names.get(domain) or cat.portal_names.get(None) or []
    used: set[str] = set()

    for item in raw:
        user_input = item.text or f"{item.name} {item.value}{' ' + item.unit if item.unit else ''}".strip()
        value = (item.value or "").strip()
        unit = canon_unit(item.unit) or item.unit
        spec = cat.find_spec(best, item.name) if best else None
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
                    pc.value, pc.unit = r.value, (r.unit or pc.unit)
            used.add(spec.name.lower())
        else:
            canon = CHAR_ALIASES.get(item.name.lower().strip())
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
                pc.name = pc.canonical_name = canonicalize_name(item.name)
                pc.source = CharSource.NEW
                pc.confidence = 0.55
                pc.notes = "Новое свойство (нет в КТРУ и выгрузках портала)"
                issues.append(Issue.make(
                    "new_property", field=pc.name, value=value, severity="warning",
                    message=f"Характеристика «{item.name}» не найдена в КТРУ и выгрузках — заведена как новая",
                ))
            if best and value and norm(item.name).startswith("материал"):
                issue = _material_issue(best, pc.name, value)
                if issue:
                    issues.append(issue)
        if value:
            have = {(i.type, i.field) for i in issues}
            for i in sanity_issues(item.name, value, item.unit, domain):
                if (i.type, i.field) not in have and not (spec and spec.is_numeric and i.type == "unit"):
                    issues.append(i)
        out.append(pc)

    # required KTRU characteristics not provided
    if best:
        windows = _part_windows(text)
        ws = morph.words(text)
        optional: list[tuple[str, CharSpec]] = []
        for k, sp in best.specs.items():
            if k in used:
                continue
            flag = morph.flag_answer(ws, sp.name) if sp.is_flag else None
            if flag:
                r = check_value(sp, flag[0], None, domain)
                if r.issue:
                    issues.append(r.issue)
                out.append(ParsedCharacteristic(
                    name=sp.name, raw_name=sp.name, canonical_name=sp.name, value=flag[0],
                    unit=None, source=CharSource.KTRU, required=sp.required, allowed=sp.allowed_enums(),
                    user_input=" ".join(ws[i] for i in flag[1]), confidence=0.8,
                    notes="Признак найден в описании",
                ))
                used.add(k)
                continue
            if not sp.required:
                if sp.enums:
                    optional.append((k, sp))
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
            allowed = _variant_values(k, sp, variants or [])
            out.append(ParsedCharacteristic(
                name=sp.name, raw_name="", canonical_name=sp.name, value="",
                unit=nu, source=CharSource.KTRU, required=True,
                allowed=allowed, min=lo, max=hi, confidence=0.0,
                notes="Обязательная характеристика КТРУ — не заполнена",
            ))
            issues.append(Issue.make(
                "missing", field=sp.name, severity="warning",
                expected=", ".join((allowed or [])[:5]) or None,
                suggestions=(allowed or [])[:3],
                message=f"Не заполнена обязательная характеристика КТРУ «{sp.name}»",
            ))
        taken = {w for c in out for w in morph.words(c.user_input)}
        for k, sp in optional:
            found = _enum_from_text(sp, _stems_for_spec(k, text, windows), full=True)
            if found and not taken & set(morph.words(found[1])):
                taken.update(morph.words(found[1]))
                out.append(ParsedCharacteristic(
                    name=sp.name, raw_name=sp.name, canonical_name=sp.name, value=found[0],
                    unit=None, source=CharSource.KTRU, required=False, allowed=sp.allowed_enums(),
                    user_input=found[1], confidence=0.7,
                    notes="Значение найдено в описании по допустимым значениям КТРУ",
                ))
    return _drop_covered(out, user_rows or set()), issues


def _drop_covered(chars: list[ParsedCharacteristic], user_rows: set[str]) -> list[ParsedCharacteristic]:
    ktru = [(norm(c.value), morph.words(c.name)) for c in chars if c.source == CharSource.KTRU and c.value]

    def covered(c: ParsedCharacteristic) -> bool:
        if c.source == CharSource.KTRU or not c.value or c.raw_name.lower() in user_rows:
            return False
        own = morph.words(c.name)
        return any(norm(c.value) == value and all(any(morph.same_stem(a, b) for b in name) for a in own)
                   for value, name in ktru)

    return [c for c in chars if not covered(c)]
