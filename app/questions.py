"""Pick one clarifying question from the differences inside a KTRU candidate group.

The matcher is not modified here. Person 1 calls `choose_question` and puts the
result on the response. This module does not call a model.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.catalog import Catalog, KtruEntry, norm


@dataclass
class QuestionChoice:
    """`field is None` means there is no useful question; `reason` explains why."""

    field: str | None
    options: list[str] = field(default_factory=list)
    eliminates: int = 0
    reason: str = ""


_EXHAUSTED = (
    "Уточнение исчерпано: оставшиеся характеристики не различают коды группы допустимыми значениями."
)


def _entries(group) -> list[KtruEntry]:
    out: list[KtruEntry] = []
    for item in group or []:
        if isinstance(item, tuple) and len(item) >= 2 and hasattr(item[1], "specs"):
            out.append(item[1])
        elif hasattr(item, "specs"):
            out.append(item)
    return out


def _spec(catalog: Catalog | None, entry: KtruEntry, name: str):
    if catalog is not None:
        return catalog.find_spec(entry, name)
    key = (name or "").lower().strip()
    return entry.specs.get(key)


def _filled_keys(filled_names) -> set[str]:
    return {norm(n) for n in (filled_names or []) if norm(n)}


def _blocked(entries: list[KtruEntry], filled: set[str], catalog: Catalog | None) -> set[str]:
    """Official characteristic names (normalized) already answered by the user."""
    blocked: set[str] = set()
    for entry in entries:
        for spec in entry.specs.values():
            if norm(spec.name) in filled:
                blocked.add(norm(spec.name))
        for name in filled:
            spec = _spec(catalog, entry, name)
            if spec is not None:
                blocked.add(norm(spec.name))
    return blocked


def choose_question(group, filled_names, catalog: Catalog | None) -> QuestionChoice:
    """Return the characteristic whose allowed values split `group` the most.

    `options` come only from the enums of that characteristic on the codes in
    the group, at most six. An already filled field is not offered. When no
    field divides the group, `field` is None and `reason` says why.
    """
    entries = _entries(group)
    if len(entries) < 2:
        return QuestionChoice(
            field=None,
            reason="Уточнение исчерпано: в группе меньше двух кодов, выбирать различающее поле не из чего.",
        )
    filled = _filled_keys(filled_names)
    blocked = _blocked(entries, filled, catalog)

    by_name: dict[str, str] = {}
    for entry in entries:
        for spec in entry.specs.values():
            by_name.setdefault(norm(spec.name), spec.name)

    best: tuple[int, int, str] | None = None
    best_options: list[str] = []
    best_distinct = 0
    for key, display in by_name.items():
        if key in blocked:
            continue
        per_code: list[list[str]] = []
        freq: Counter[str] = Counter()
        for entry in entries:
            spec = _spec(catalog, entry, display)
            enums = list(dict.fromkeys(spec.enums)) if spec is not None and spec.enums else []
            per_code.append(enums)
            for value in {norm(v) for v in enums if norm(v)}:
                freq[value] += 1
        present = [enums for enums in per_code if enums]
        union = [v for v in freq if v]
        if len(union) < 2 or len(present) < 2:
            continue
        signature = [frozenset(norm(v) for v in enums) for enums in present]
        if len(set(signature)) < 2:
            continue
        keep = max(freq.values()) if freq else 0
        eliminates = len(entries) - keep
        if eliminates < 1:
            continue
        rank = (len(union), eliminates, display)
        # Larger variety wins. Equal variety breaks toward the name so the choice is stable.
        better = best is None or rank[0] > best[0] or (
            rank[0] == best[0] and (rank[1] > best[1] or (rank[1] == best[1] and display < best[2]))
        )
        if not better:
            continue
        ordered = sorted(freq, key=lambda v: (-freq[v], v))
        # Keep the original spelling of the most common surface form.
        surface: dict[str, str] = {}
        for enums in per_code:
            for value in enums:
                surface.setdefault(norm(value), value)
        options = [surface[v] for v in ordered if v in surface][:6]
        best = (len(union), eliminates, display)
        best_options = options
        best_distinct = len(union)

    if best is None:
        return QuestionChoice(field=None, reason=_EXHAUSTED)
    return QuestionChoice(
        field=best[2],
        options=best_options,
        eliminates=best[1],
        reason=(
            f"Поле «{best[2]}» различает коды группы: {best_distinct} допустимых значений, "
            f"один ответ снимает до {best[1]} кодов."
        ),
    )
