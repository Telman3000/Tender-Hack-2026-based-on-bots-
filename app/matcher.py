"""Stepwise narrowing of KTRU candidates: domain -> name -> OKPD2 group -> each characteristic."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein  # noqa: F401  (kept for typo helpers)

from app.catalog import Catalog, KtruEntry, norm, tokens
from app.config import CHAR_ALIASES
from app.models import Candidate, CharCheck, Issue, KtruCandidate, NarrowingStep
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
QUALIFIER_STEMS = (
    "кож", "=мех", "=меха", "=мехом", "мехов", "детск", "женск", "мужск", "резин", "пластик", "пациент", "хирург", "операцион",
    "процедур", "изолир", "одноразов", "многоразов", "ученич", "лаборатор", "клавиш", "библиотеч",
    "механическ", "одежд", "посуд", "хлеб", "игрушек", "реактив", "холодильн", "сушильн",
    "приставн", "журнальн", "обеденн", "компьютерн", "раскройн", "туристическ", "президиум",
)
# head noun -> generic KTRU name used for that kind of goods
HEAD_SYNONYMS = {
    "ботинк": "обувь специальная кожаная", "полуботинк": "обувь специальная кожаная",
    "сапог": "обувь специальная", "туфл": "обувь", "кроссовк": "обувь",
}
OK_MARGIN = 8.0
MATERIAL_CONFLICTS = (("металл", "дерев"), ("дерев", "металл"), ("пластик", "металл"), ("пластик", "дерев"))
PURPOSE_EXPANSIONS = {"документ": ("архивн", "картотечн", "документ"), "офисн": ("письменн",)}


def canonical_label(cnt: Counter, raw_name: str) -> str:
    """KTRU name of the characteristic (most common among candidates), else capitalised alias."""
    if cnt:
        return sorted(cnt.items(), key=lambda x: (-x[1], x[0]))[0][0]
    alias = CHAR_ALIASES.get(raw_name.strip().lower())
    return alias or (raw_name[:1].upper() + raw_name[1:])


WORKWEAR_HEADS = ("костюм", "куртк", "брюк", "полукомбинезон", "комбинезон", "жилет", "халат", "фартук")
PROTECTION_STEMS = ("изолир", "защит", "хирург", "сигнальн", "огнестойк", "термостойк", "кислот")


def work_signal(query: str) -> bool:
    return any(w.startswith(st) for w in norm(query).split() for st in WORK_STEMS)


# hand tools that have no own KTRU position
HAND_SYNONYMS = {"отвертк": "инструмент ручной прочий", "отвёртк": "инструмент ручной прочий",
                 "напильник": "инструмент ручной прочий", "ножовк": "инструмент ручной прочий"}


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
    margin: float = 999.0
    # Person-1 search contract
    area_size: int = 0
    checked_count: int = 0
    compatible_count: int = 0
    completeness: str = "partial"  # full | partial
    checks: list[CharCheck] = field(default_factory=list)
    input_conflict: bool = False
    distinct_name_count: int = 0
    area_pass_done: bool = False
    shortlist_codes: list[str] = field(default_factory=list)  # before final char elimination


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
        if len(nw) < 4 or nw in vocab or nw.isdigit() or cat.known_form(nw, domain):
            out.append(w)
            continue
        m = process.extractOne(nw, cat.vocab_list(domain), scorer=fuzz.ratio, score_cutoff=80)
        if m and m[0] != nw and m[0][:-2] != nw[:-2]:  # same stem, other ending = inflection, not a typo
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
    text: str | None = None,
) -> NarrowResult:
    from app.unify import _enum_from_text, _text_stems

    text_stems = _text_stems(text) if text else None
    res = NarrowResult()
    pool = cat.pool(domain if domain_detected else None)
    n0 = len(pool)
    # Area = all positions of the selected domain (short name list is display order only)
    res.area_size = n0
    res.compatible_count = n0
    res.steps.append(NarrowingStep(
        step=1, label="Домен", stage="domain", remaining=n0, removed=0,
        reason=f"Область поиска КТРУ: домен «{DOMAIN_LABEL.get(domain, domain)}» ({n0} позиций)",
        note=f"{n0} позиций КТРУ в скоупе",
    ))
    if not pool:
        res.issues.append(Issue.make("missing", "Индекс КТРУ пуст — соберите catalog.db", severity="error"))
        res.completeness = "full"
        res.area_pass_done = True
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
    head_q = norm(query).split()[0] if norm(query) else ""
    if domain in ("tools", None) and not power_signal(product, raw):
        hsyn = next((v for k, v in HAND_SYNONYMS.items() if head_q.startswith(k)), None)
        if hsyn:
            s1 = np.maximum(s1, _scores(hsyn, names, toks) + 20.0
                            * np.array([n.startswith(hsyn) for n in names], dtype=float))
    if domain in ("tools", None) and power_signal(product, raw):
        head = norm(query).split()[0] if norm(query) else ""
        syn = next((v for k, v in POWER_SYNONYMS.items() if head.startswith(k)), None)
        if syn:
            s1 = np.maximum(s1, _scores(syn + " " + query, names, toks) * 0.95)
        okp = cat.okpd_for(pool)
        s1 = s1 + np.where(np.char.startswith(okp, "28.24"), 20.0,
                           np.where(np.char.startswith(okp, "25.7"), -15.0, 0.0))
        res.power_tool = True
    qws = norm(query).split()
    head0 = qws[0] if qws else ""
    syn = next((v for k, v in HEAD_SYNONYMS.items() if head0.startswith(k)), None)
    if syn and domain in ("clothing", None):
        s1 = np.maximum(s1, _scores(syn + " " + query, names, toks) * 0.95)
    if domain in ("clothing", None) and work_signal(query):
        if any(head0.startswith(h) for h in WORKWEAR_HEADS) and not any(
            w.startswith(p) for w in qws for p in PROTECTION_STEMS
        ):
            gender = "женская" if any(w.startswith("женск") for w in qws) else "мужская"
            s1 = np.maximum(s1, _scores(f"спецодежда {gender} " + query, names, toks) * 1.0 + 10.0
                            * np.array([n.startswith("спецодежда " + gender) for n in names], dtype=float))
        okp = cat.okpd_for(pool)
        s1 = s1 + np.where(np.char.startswith(okp, "14.12") | np.char.startswith(okp, "15.20.3"), 30.0,
                           np.where(np.char.startswith(okp, "14.14") | np.char.startswith(okp, "14.19"), -20.0, 0.0))
    # contradicting materials: «металлический» query vs «деревянный» position
    for a, b in MATERIAL_CONFLICTS:
        if any(w.startswith(a) for w in qws):
            s1 = s1 - 25.0 * cat.qualifier_mask(pool, b)
    # purpose -> KTRU wording («для документов» -> «архивный», «картотечный»)
    for stem, words in PURPOSE_EXPANSIONS.items():
        if any(w.startswith(stem) for w in qws):
            for wd in words:
                s1 = s1 + 12.0 * cat.qualifier_mask(pool, wd)
    # qualifiers in the KTRU name not backed by the query
    pen = np.zeros(len(names))
    for st in QUALIFIER_STEMS:
        exact = st.startswith("=")
        if any((w == st[1:]) if exact else w.startswith(st) for w in qws):
            continue
        pen += cat.qualifier_mask(pool, st)
    s1 = s1 - 25.0 * np.minimum(pen, 2)
    order = np.argsort(-s1, kind="stable")
    best_s = float(s1[order[0]]) if len(order) else 0.0
    # Short list by name — порядок показа, не сужение области
    short_local = [int(i) for i in order[:80] if s1[i] >= NAME_MIN and s1[i] >= best_s - NAME_BAND]
    if not short_local and len(order):
        short_local = [int(order[0])]
    name_scores = {pool[i]: float(s1[i]) for i in range(len(pool))}
    short_pool = [pool[i] for i in short_local]
    # Full name shortlist (not only top-8 shown) — QA reads search.shortlist / debug.search
    res.shortlist_codes = [cat.entries[i].code for i in short_pool]
    res.steps.append(NarrowingStep(
        step=2, label="Наименование", stage="name_match", remaining=res.area_size,
        removed=0,
        reason=f"Порядок показа по сходству с «{query}» (область {res.area_size} не сужается)",
        removed_codes=[],
        top=[_cand(cat.entries[pool[i]], float(s1[i])) for i in short_local[:8]],
        note=f"Короткий список для UI: {len(short_local)}; область поиска: {res.area_size}",
    ))
    if best_s < NAME_MIN and not raw:
        res.issues.append(Issue.make(
            "missing", field="Наименование", value=product,
            message="Не удалось сопоставить описание ни с одной позицией КТРУ в скоупе",
            suggestions=["Уточните тип товара (стол/стул/куртка/дрель…)"], severity="warning",
        ))
        res.next_steps += ["Добавьте явное название товара", "Укажите 2–3 ключевые характеристики"]
        res.completeness = "full" if domain_detected else "partial"
        res.area_pass_done = True
        res.compatible_count = res.area_size
        return res

    # OKPD2 — только влияет на ранжирование короткого списка, область не режем
    lead_score = float(s1[short_local[0]]) if short_local else 0.0
    groups = {(cat.entries[pool[i]].okpd2 or "")[:8]
              for i in short_local if float(s1[i]) >= lead_score - 8}
    res.steps.append(NarrowingStep(
        step=3, label="ОКПД2", stage="okpd2", remaining=res.area_size, removed=0,
        reason="Группы ОКПД2 лидеров (ранжирование): " + ", ".join(sorted(g for g in groups if g)),
        removed_codes=[],
        top=[_cand(cat.entries[pool[i]], float(s1[i])) for i in short_local[:8]],
    ))

    # --- Full-area characteristic pass (Person-1) ---
    # origin=new не участвует: характеристика без CharSpec у позиции = UNKNOWN, код остаётся
    compatible: set[int] = set(pool)
    eliminated_checks: list[CharCheck] = []
    matched: dict[int, list[str]] = {i: [] for i in pool}
    score_boost: dict[int, float] = {i: 0.0 for i in pool}
    step_no = 4
    constraints_applied = 0

    for kv in raw:
        exp_dim = expected_dimension(kv.name)
        if kv.unit and exp_dim and dimension(kv.unit) and dimension(kv.unit) != exp_dim:
            continue  # wrong unit: validation reports; must not filter
        # polarity=negative + «нет»: не инвертировать в «да»; отсутствие характеристики ≠ запрет
        neg_absent = (getattr(kv, "polarity", "positive") == "negative"
                      and norm(kv.value) in {"нет", "отсутствует", "без"})
        label_cnt: Counter[str] = Counter()
        has_spec = 0
        fail_codes: list[str] = []
        still: set[int] = set()
        for idx in compatible:
            e = cat.entries[idx]
            sp = cat.find_spec(e, kv.name)
            if sp is None:
                # нет характеристики у позиции → UNKNOWN, код остаётся
                still.add(idx)
                continue
            has_spec += 1
            label_cnt[sp.name] += 1
            res.checked_count += 1
            # keep value «нет» as-is (never flip to «да»)
            r = check_value(sp, kv.value, kv.unit, domain, emit=False)
            if r.ok:
                score_boost[idx] += 8 if (sp.enums or sp.is_numeric) else 4
                matched[idx].append(sp.name)
                still.add(idx)
            elif neg_absent:
                # negative fact: codes that have the char but don't accept «нет» stay
                # (absence already kept above); do not hard-eliminate whole area on «без X»
                still.add(idx)
            else:
                fail_codes.append(e.code)
                reason = (r.issue.message if r.issue else
                          f"«{kv.name}»={kv.value} недопустимо для {e.code}")
                eliminated_checks.append(CharCheck(
                    code=e.code, char_name=sp.name, outcome="FAIL", reason=reason,
                ))
        if not has_spec:
            continue  # свойство ни у кого в КТРУ — как origin=new/portal, не отсекает
        constraints_applied += 1
        removed_n = len(compatible) - len(still)
        compatible = still
        reason = (
            f"«{kv.value}{' ' + kv.unit if kv.unit else ''}» FAIL у {len(fail_codes)} кодов области"
            if fail_codes else
            f"Характеристика подтверждена у {has_spec} кодов области"
        )
        # топ для UI — по имени из короткого списка ∩ compatible
        top_idx = [i for i in short_pool if i in compatible][:8] or sorted(
            compatible, key=lambda i: -(name_scores.get(i, 0) + score_boost.get(i, 0))
        )[:8]
        res.steps.append(NarrowingStep(
            step=step_no, label=canonical_label(label_cnt, kv.name), stage="char_filter",
            remaining=len(compatible), removed=removed_n, reason=reason,
            removed_codes=fail_codes[:10],
            top=[_cand(cat.entries[i], name_scores.get(i, 0) + score_boost.get(i, 0), matched[i])
                 for i in top_idx],
        ))
        step_no += 1

    res.area_pass_done = True
    res.completeness = "full" if domain_detected else "partial"
    res.compatible_count = len(compatible)

    if not compatible:
        res.checks = eliminated_checks[:50]
        res.best = None
        res.group = []
        res.shown = []
        res.distinct_name_count = 0
        res.steps.append(NarrowingStep(
            step=step_no, label="Итог", stage="final", remaining=0, removed=res.area_size,
            reason="NO_MATCH_IN_SNAPSHOT: после полного прохода области совместимых кодов нет",
            note="compatible_count=0",
        ))
        return res

    # Rank compatible codes (name score + char boost)
    ranked = sorted(
        compatible,
        key=lambda i: (-(name_scores.get(i, 0.0) + score_boost.get(i, 0.0)), cat.entries[i].code),
    )
    # soft OKPD2 preference among leaders
    if groups:
        pref = [i for i in ranked if (cat.entries[i].okpd2 or "")[:8] in groups]
        if pref:
            ranked = pref + [i for i in ranked if i not in pref]

    if text_stems is not None:
        for i in ranked[:80]:
            for sp in cat.entries[i].specs.values():
                if sp.required and sp.enums and _enum_from_text(sp, text_stems):
                    score_boost[i] += 6.0
                    matched[i].append(sp.name)
        ranked = sorted(
            compatible,
            key=lambda i: (-(name_scores.get(i, 0.0) + score_boost.get(i, 0.0)), cat.entries[i].code),
        )

    cands = [
        [name_scores.get(i, 0.0) + score_boost.get(i, 0.0), cat.entries[i], matched[i]]
        for i in ranked
    ]
    top = cands[0][0]
    group = [(s, e) for s, e, _ in cands if s >= top - GROUP_BAND]
    # Prefer name-shortlist leaders inside the score band for display grouping
    group_codes_short = {cat.entries[i].code for i in short_pool}
    group_disp = [(s, e) for s, e in group if e.code in group_codes_short] or group
    res.group = group_disp if group_disp else group
    res.best = res.group[0][1]
    distinct_names = {e.name for _, e in res.group}
    res.distinct_name_count = len(distinct_names)
    other = next((sc for sc, e, _ in cands if e.name != res.best.name), None)
    res.margin = (top - other) if other is not None else 999.0
    final_note = "Конечный код выбран"
    if len(distinct_names) > 1:
        final_note = f"Конкурируют {len(res.group)} кодов — нужно уточнение"
        res.issues.append(Issue.make(
            "ambiguous",
            f"Найдено {len(res.group)} близких кодов КТРУ — однозначно определить нельзя",
            suggestions=["Добавьте отличительные характеристики из топ-кандидатов"], severity="warning",
        ))
    elif len(res.group) > 1:
        final_note = f"Группа вариаций «{res.best.name}»: {len(res.group)} кодов"
    if len(res.group) > 1:
        user = {kv.name.lower() for kv in raw}
        cnt: Counter[str] = Counter()
        vals: dict[str, set] = {}
        for _, e in res.group[:10]:
            for k, sp in e.specs.items():
                if k in user:
                    continue
                cnt[sp.name] += 1
                vals.setdefault(sp.name, set()).update(sp.enums[:20] or [str(sp.ranges[:1])])
        ranked_q = sorted(cnt, key=lambda n: (-(len(vals.get(n, ())) > 1), -cnt[n], n))
        for n in ranked_q[:3]:
            res.next_steps.append(f"Уточните: {n}")

    seen_n: set[str] = set()
    firsts, rest = [], []
    extra = [(s_, e) for s_, e, _ in cands[len(res.group):len(res.group) + 10]]
    for s_, e in list(res.group) + extra:
        (rest if e.name in seen_n else firsts).append((s_, e))
        seen_n.add(e.name)
    shown = (firsts[:3] + [x for x in res.group if x not in firsts[:3]])[:8]
    res.shown = shown

    # checks: только показанные кандидаты + реально отсеянные FAIL (не все 3391)
    shown_codes = {e.code for _, e in shown}
    checks_out: list[CharCheck] = []
    for ch in eliminated_checks:
        if ch.code in shown_codes or ch.outcome == "FAIL":
            checks_out.append(ch)
    for _, e in shown:
        for kv in raw:
            sp = cat.find_spec(e, kv.name)
            if sp is None:
                checks_out.append(CharCheck(
                    code=e.code, char_name=kv.name, outcome="UNKNOWN",
                    reason="Характеристика отсутствует у позиции КТРУ",
                ))
            else:
                r = check_value(sp, kv.value, kv.unit, domain, emit=False)
                if r.ok and not any(c.code == e.code and c.char_name == sp.name and c.outcome == "PASS"
                                    for c in checks_out):
                    checks_out.append(CharCheck(
                        code=e.code, char_name=sp.name, outcome="PASS", reason=None,
                    ))
    # cap + dedupe
    seen_ck: set[tuple] = set()
    uniq: list[CharCheck] = []
    for c in checks_out:
        key = (c.code, c.char_name, c.outcome)
        if key in seen_ck:
            continue
        seen_ck.add(key)
        uniq.append(c)
        if len(uniq) >= 80:
            break
    res.checks = uniq

    res.steps.append(NarrowingStep(
        step=step_no, label="Итог", stage="final" if len(distinct_names) == 1 else "ambiguous",
        remaining=res.compatible_count, removed=res.area_size - res.compatible_count,
        reason=final_note, removed_codes=[e.code for _, e, _ in cands[len(res.group):][:10]],
        top=[_cand(e, s) for s, e in shown], note=final_note,
    ))
    return res


def candidates_view(group: list[tuple[float, KtruEntry]]) -> list[Candidate]:
    return [Candidate(code=e.code, name=e.name, score=round(float(s), 2)) for s, e in group[:5]]
