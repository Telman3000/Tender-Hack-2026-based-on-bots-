"""Characteristic unification: KTRU (of the chosen code) -> portal frequency -> new property."""
from __future__ import annotations

from rapidfuzz import fuzz, process

from app.catalog import Catalog, KtruEntry
from app.config import CHAR_ALIASES
from app.models import CharSource, Issue, ParsedCharacteristic
from app.parser import RawKV, canonicalize_name
from app.units import canon_unit
from app.validate import check_value, is_numeric_spec, numeric_view, sanity_issues


def unify_characteristics(
    cat: Catalog,
    raw: list[RawKV],
    domain: str | None,
    best: KtruEntry | None,
    user_rows: set[str] | None = None,
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
        if value:
            have = {(i.type, i.field) for i in issues}
            for i in sanity_issues(item.name, value, item.unit, domain):
                if (i.type, i.field) not in have and not (spec and spec.is_numeric and i.type == "unit"):
                    issues.append(i)
        out.append(pc)

    # required KTRU characteristics not provided
    if best:
        for k, sp in best.specs.items():
            if not sp.required or k in used:
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
    return out, issues
