"""Stepwise narrowing of KTRU candidates: domain -> name -> OKPD2 group -> each characteristic."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein  # noqa: F401  (kept for typo helpers)

from app.catalog import Catalog, KtruEntry, norm, tokens
from app.models import Candidate, Issue, KtruCandidate, NarrowingStep
from app.parser import RawKV
from app.units import dimension, expected_dimension
from app.validate import check_value

DOMAIN_LABEL = {"furniture": "мебель", "clothing": "одежда", "tools": "инструменты", None: "все"}
NAME_MIN = 35.0
NAME_BAND = 25.0
GROUP_BAND = 12.0

# Power tools (ОКПД2 28.24) vs hand tools (25.7x)
POWER_STEMS = ("аккумулятор", "электр", "отбойн", "пневмат", "сетев", "беспровод", "бесщеточ",
               "бесщёточ", "ударн", "перфорат", "гайковерт", "гайковёрт", "болгарк", "лобзик")
POWER_UNITS = {"Вт", "кВт", "В", "А·ч", "мА·ч", "об/мин"}
# hand-tool head noun -> name of the matching power-tool KTRU position
POWER_SYNONYMS = {
    "отвертк": "шуруповерт",
    "отвёртк": "шуруповерт",
    "гайковерт": "шуруповерт",
    "молоток": "инструменты ручные электрические",
    "перфоратор": "инструменты ручные электрические",
    "болгарк": "шлифмашина",
    "пила": "электролобзик пила",
}


# Workwear: "рабочий", "для уборщиц" -> спецодежда 14.12 / спецобувь 15.20.3
WORK_STEMS = ("рабоч", "спец", "уборщ", "производствен", "защитн", "сигнальн", "охран", "строител")
# qualifiers in KTRU names that must be backed by the query ("из кожи", "детская", "с верхом из меха")
QUALIFIER_STEMS = ("кож", "мех", "детск", "женск", "мужск")


def work_signal(query: str) -> bool:
    return any(w.startswith(st) for w in norm(query).split() for st in WORK_STEMS)


def power_signal(query: str, raw: list[RawKV]) -> bool:
    ws = norm(query).split()
    if any(w.startswith(st) for w in ws for st in POWER_STEMS):
        return True
    return any(kv.unit in POWER_UNITS for kv in raw)


@dataclass
class NarrowResult:
    steps: list[NarrowingStep] = field(default_factory=list)
    best: KtruEntry | None = None
    group: list[tuple[float, KtruEntry]] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    query: str = ""
    shown: list = field(default_factory=list)
    power_tool: bool = False


def score_name(query: str, candidate: str) -> float:
    """Kept for compatibility: single-pair score (same formula as vectorised one)."""
    qn, cn = norm(query), norm(candidate)
    if not qn or not cn:
        return 0.0
    qt, ct = tokens(qn), tokens(cn)
    overlap = len(qt & ct) / max(1, len(qt))
    return 0.55 * fuzz.token_set_ratio(qn, cn) + 0.25 * fuzz.partial_ratio(qn, cn) + 20.0 * overlap


def _scores(query: str, names: list[str], toks: list[frozenset[str]]) -> np.ndarray:
    qn = norm(query)
    if not qn or not names:
        return np.zeros(len(names))
    ts = process.cdist([qn], names, scorer=fuzz.token_set_ratio, workers=1)[0]
    pr = process.cdist([qn], names, scorer=fuzz.partial_ratio, workers=1)[0]
    qt = tokens(qn)
    ov = np.array([len(qt & t) / max(1, len(qt)) for t in toks]) if qt else np.zeros(len(names))
    base = 0.55 * ts + 0.25 * pr + 20.0 * ov
    # head noun: first query word vs first word of the KTRU name ("стол" ≠ "стеллаж", "стул" ≠ "стол")
    head = qn.split()[0]
    if len(head) >= 3:
        firsts = [n.split()[0] if n else "" for n in names]
        hr = process.cdist([head], firsts, scorer=fuzz.ratio, workers=1)[0]
        stem = head[:5] if len(head) > 5 else head
        same = np.array([f.startswith(stem) or stem.startswith(f[:5]) if f else False for f in firsts])
        base = base + np.where(same | (hr >= 90), 25.0, np.where(hr >= 80, 10.0, -10.0))
    return base


def correct_query(cat: Catalog, query: str, domain: str | None) -> tuple[str, list[Issue]]:
    """Cheap typo fix: query words unknown to the domain vocabulary -> closest vocabulary word."""
    vocab = cat.vocab(domain)
    out, issues = [], []
    for w in query.split():
        nw = norm(w)
        if len(nw) < 4 or nw in vocab or nw.isdigit():
            out.append(w)
            continue
        m = process.extractOne(nw, cat.vocab_list(domain), scorer=fuzz.ratio, score_cutoff=80)
        if m and m[0] != nw:
            out.append(m[0])
            issues.append(Issue.make(
                "typo", field="Наименование", value=w, expected=m[0], suggestions=[m[0]],
                message=f"Возможная опечатка: «{w}» → «{m[0]}»", severity="warning",
            ))
        else:
            out.append(w)
    return " ".join(out), issues


def _cand(e: KtruEntry, score: float, matched: list[str] | None = None) -> KtruCandidate:
    return KtruCandidate(code=e.code, name=e.name, okpd2=e.okpd2, score=round(float(score), 2),
                         required_chars=e.required, matched_chars=matched or [])


def narrow_ktru(
    cat: Catalog,
    product: str,
    raw: list[RawKV],
    domain: str | None,
    domain_detected: bool = True,
) -> NarrowResult:
    res = NarrowResult()
    pool = cat.pool(domain if domain_detected else None)
    n0 = len(pool)
    res.steps.append(NarrowingStep(
        step=1, label="Домен", stage="domain", remaining=n0, removed=0,
        reason=f"Начальный пул КТРУ: домен «{DOMAIN_LABEL.get(domain, domain)}»",
        note=f"{n0} позиций КТРУ в скоупе",
    ))
    if not pool:
        res.issues.append(Issue.make("missing", "Индекс КТРУ пуст — соберите catalog.db", severity="error"))
        return res

    query, typo_issues = correct_query(cat, product, domain)
    res.issues.extend(typo_issues)
    # enrich by closest portal STE names (sorted tokens -> deterministic)
    ste = cat.ste_names.get(domain) or []
    if ste and len(norm(query)) >= 3:
        hits = process.extract(norm(query), ste, scorer=fuzz.token_set_ratio, limit=3, score_cutoff=80)
        extra = []
        for name, _sc, _i in hits:
            extra.extend(sorted(tokens(name) - tokens(query))[:3])
        enriched = query + " " + " ".join(dict.fromkeys(extra)) if extra else query
    else:
        enriched = query
    res.query = query

    names, toks = cat.names_for(pool)
    s1 = _scores(query, names, toks)
    if enriched != query:
        s1 = np.maximum(s1, _scores(enriched, names, toks) * 0.9)
    if domain in ("tools", None) and power_signal(product, raw):
        head = norm(query).split()[0] if norm(query) else ""
        syn = next((v for k, v in POWER_SYNONYMS.items() if head.startswith(k)), None)
        if syn:
            s1 = np.maximum(s1, _scores(syn + " " + query, names, toks) * 0.95)
        okp = cat.okpd_for(pool)
        s1 = s1 + np.where(np.char.startswith(okp, "28.24"), 20.0,
                           np.where(np.char.startswith(okp, "25.7"), -15.0, 0.0))
        res.power_tool = True
    if domain in ("clothing", None):
        qws = norm(product).split()
        if work_signal(product):
            okp = cat.okpd_for(pool)
            s1 = s1 + np.where(np.char.startswith(okp, "14.12") | np.char.startswith(okp, "15.20.3"), 30.0, 0.0)
        pen = np.zeros(len(names))
        for st in QUALIFIER_STEMS:
            if any(w.startswith(st) for w in qws):
                continue
            pen += np.array([any(w.startswith(st) for w in n.split()[1:]) for n in names], dtype=float)
        s1 = s1 - 15.0 * pen
    order = np.argsort(-s1, kind="stable")
    best_s = float(s1[order[0]])
    keep_idx = [int(i) for i in order[:80] if s1[i] >= NAME_MIN and s1[i] >= best_s - NAME_BAND]
    removed = [int(i) for i in order if int(i) not in set(keep_idx)]
    cands: list[list] = [[float(s1[i]), cat.entries[pool[i]], []] for i in keep_idx]
    res.steps.append(NarrowingStep(
        step=2, label="Наименование", stage="name_match", remaining=len(cands),
        removed=n0 - len(cands),
        reason=f"Сопоставление с наименованием «{query}»",
        removed_codes=[cat.entries[pool[i]].code for i in removed[:10]],
        top=[_cand(e, s) for s, e, _ in cands[:8]],
        note=f"После сопоставления названия из {n0} позиций осталось {len(cands)}",
    ))
    if not cands:
        res.issues.append(Issue.make(
            "missing", field="Наименование", value=product,
            message="Не удалось сопоставить описание ни с одной позицией КТРУ в скоупе",
            suggestions=["Уточните тип товара (стол/стул/куртка/дрель…)"], severity="error",
        ))
        res.next_steps += ["Добавьте явное название товара", "Укажите 2–3 ключевые характеристики"]
        return res

    # OKPD2 group: keep groups present among the leaders
    lead = cands[0][0]
    groups = {(e.okpd2 or "")[:8] for s, e, _ in cands if s >= lead - 8}
    kept = [c for c in cands if (c[1].okpd2 or "")[:8] in groups]
    rem = [c for c in cands if c not in kept]
    res.steps.append(NarrowingStep(
        step=3, label="ОКПД2", stage="okpd2", remaining=len(kept), removed=len(rem),
        reason="Группы ОКПД2 лидеров: " + ", ".join(sorted(g for g in groups if g)),
        removed_codes=[c[1].code for c in rem[:10]],
        top=[_cand(e, s) for s, e, _ in kept[:8]],
    ))
    cands = kept

    # Characteristics: drop codes where the value is impossible (never drop all)
    step_no = 4
    for kv in raw:
        exp_dim = expected_dimension(kv.name)
        if kv.unit and exp_dim and dimension(kv.unit) and dimension(kv.unit) != exp_dim:
            continue  # wrong unit: reported by validation, must not filter codes
        ok_c, bad_c, has_spec = [], [], 0
        for c in cands:
            sp = cat.find_spec(c[1], kv.name)
            if sp is None:
                ok_c.append(c)
                continue
            has_spec += 1
            r = check_value(sp, kv.value, kv.unit, domain, emit=False)
            if r.ok:
                c[0] += 8 if (sp.enums or sp.is_numeric) else 4
                c[2].append(sp.name)
                ok_c.append(c)
            else:
                bad_c.append(c)
        if not has_spec:
            continue
        if bad_c and ok_c:
            cands = ok_c
            reason = f"«{kv.value}{' ' + kv.unit if kv.unit else ''}» недопустимо для {len(bad_c)} кодов"
        elif bad_c:
            reason = "Значение не подходит ни одному коду — коды не отсеяны, см. ошибки"
            bad_c = []
        else:
            reason = f"Характеристика есть у {has_spec} кодов, значение допустимо"
        res.steps.append(NarrowingStep(
            step=step_no, label=kv.name, stage="char_filter", remaining=len(cands),
            removed=len(bad_c), reason=reason, removed_codes=[c[1].code for c in bad_c[:10]],
            top=[_cand(e, s, m) for s, e, m in sorted(cands, key=lambda x: -x[0])[:8]],
        ))
        step_no += 1

    cands.sort(key=lambda x: (-x[0], x[1].code))
    top = cands[0][0]
    group = [(s, e) for s, e, _ in cands if s >= top - GROUP_BAND]
    res.group = group
    res.best = cands[0][1]
    distinct_names = {e.name for _, e in group}
    final_note = "Конечный код выбран"
    if len(distinct_names) > 1:
        final_note = f"Конкурируют {len(group)} кодов — нужно уточнение"
        res.issues.append(Issue.make(
            "ambiguous",
            f"Найдено {len(group)} близких кодов КТРУ — однозначно определить нельзя",
            suggestions=["Добавьте отличительные характеристики из топ-кандидатов"], severity="warning",
        ))
    elif len(group) > 1:
        final_note = f"Группа вариаций «{res.best.name}»: {len(group)} кодов"
    # most discriminating characteristic among the group
    if len(group) > 1:
        user = {kv.name.lower() for kv in raw}
        cnt: Counter[str] = Counter()
        vals: dict[str, set] = {}
        for _, e in group[:10]:
            for k, sp in e.specs.items():
                if k in user:
                    continue
                cnt[sp.name] += 1
                vals.setdefault(sp.name, set()).update(sp.enums[:20] or [str(sp.ranges[:1])])
        ranked = sorted(cnt, key=lambda n: (-(len(vals.get(n, ())) > 1), -cnt[n], n))
        for n in ranked[:3]:
            res.next_steps.append(f"Уточните: {n}")
    # show distinct names first so the UI/top-3 covers alternative groups
    seen_n: set[str] = set()
    firsts, rest = [], []
    for s_, e in group + [(s_, e) for s_, e, _ in cands[len(group):len(group) + 10]]:
        (rest if e.name in seen_n else firsts).append((s_, e))
        seen_n.add(e.name)
    shown = (firsts[:3] + [x for x in group if x not in firsts[:3]])[:8]
    res.shown = shown
    res.steps.append(NarrowingStep(
        step=step_no, label="Итог", stage="final" if len(distinct_names) == 1 else "ambiguous",
        remaining=len(group), removed=len(cands) - len(group),
        reason=final_note, removed_codes=[e.code for _, e, _ in cands[len(group):][:10]],
        top=[_cand(e, s) for s, e in shown], note=final_note,
    ))
    return res


def candidates_view(group: list[tuple[float, KtruEntry]]) -> list[Candidate]:
    return [Candidate(code=e.code, name=e.name, score=round(float(s), 2)) for s, e in group[:5]]
