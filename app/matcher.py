"""Stepwise narrowing of KTRU candidates: domain -> name -> OKPD2 group -> each characteristic."""
from __future__ import annotations

import re

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein  # noqa: F401  (kept for typo helpers)

from app.catalog import Catalog, KtruEntry, norm, stems_of, tokens
from app.config import CHAR_ALIASES
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


# A named hand tool stays a hand tool: one electrical characteristic must not reclassify it.
_HAND_HEADS = ("молоток", "молотк", "отвертк", "отвёртк", "напильник", "ножовк", "киянк", "зубил", "шпател")


def power_signal(query: str, raw: list[RawKV]) -> bool:
    ws = norm(query).split()
    manual = any(w.startswith("ручн") for w in ws)
    electric = any(w.startswith(st) for w in ws for st in ("электр", "аккумулятор", "сетев", "пневмат"))
    if manual and not electric:
        return False  # «лобзик ручной» is not a power tool just because the stem is in POWER_STEMS
    if any(w.startswith(st) for w in ws for st in POWER_STEMS):
        return True
    head = ws[0] if ws else ""
    if any(head.startswith(h) for h in _HAND_HEADS):
        return False
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
    anchored: bool = True  # head noun or an explicit synonym supports the winner


def _name_words_supported(entry_name: str, query: str) -> bool:
    """False when the KTRU title adds a word the description never said («игровой», «вентури»)."""
    q = [w for w in norm(query).split() if len(w) >= 4]
    for w in norm(entry_name).split():
        if len(w) < 5 or w in {"для", "под"}:
            continue
        if any(w.startswith(x[:5]) or x.startswith(w[:5]) for x in q):
            continue
        return False
    return True


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


def _typo_fix(cat: Catalog, w: str, domain: str | None, cutoff: float) -> str | None:
    nw = norm(w)
    if len(nw) < 4 or not nw.isalpha() or nw in cat.any_words(domain) or cat.known_form(nw, domain):
        return None
    cands = process.extract(nw, cat.vocab_list(domain), scorer=fuzz.ratio, score_cutoff=cutoff, limit=10)
    if not cands:
        return None
    # fewest edits first; same length (substitution, e.g. voiced/voiceless swap) before insert/delete
    best = min(cands, key=lambda c: (Levenshtein.distance(nw, c[0]), c[0][-2:] != nw[-2:],
                                     abs(len(c[0]) - len(nw)), -c[1], c[0]))[0]
    if best == nw or stems_of(best) & stems_of(nw):  # same stem = inflection, not a typo
        return None
    if Levenshtein.distance(nw, best) > 2:  # «резиновый» is not «бензиновый»
        return None
    return best


def correct_query(cat: Catalog, query: str, domain: str | None, text: str = "") -> tuple[str, list[Issue]]:
    """Typo fix against the trusted vocabulary (KTRU + frequent portal words).

    Product-name words are replaced in the query; other description words only get a warning.
    Catches doubled/missing letters and voiced/voiceless swaps («производственый», «Шуруповерд»).
    """
    out, issues = [], []
    seen: set[str] = set()
    for k, w in enumerate(query.split()):
        brand = (not re.fullmatch(r"[А-Яа-яЁё\-]+", w)) or (k > 0 and w[:1].isupper()) or (len(w) > 1 and w.isupper())
        # First word: «Малаток» is two substitutions from «молоток» (ratio ~71), still a typo.
        fix = None if brand else _typo_fix(cat, w, domain, 70 if k == 0 else 80)
        if fix and k == 0 and norm(w)[:1] != norm(fix)[:1]:
            fix = None
        out.append(fix or w)
        seen.add(norm(w))
        if fix:
            issues.append(Issue.make(
                "typo", field="Наименование", value=w, expected=fix, suggestions=[fix],
                message=f"Возможная опечатка: «{w}» → «{fix}»", severity="warning",
            ))
    for m_ in re.finditer(r"[\w\-\"«»]+", text or ""):
        w = m_.group(0)
        # skip brands/models (capitalised mid-text, quoted, with digits/latin) and hyphenated compounds
        if (not re.fullmatch(r"[А-Яа-яЁё]{6,}", w) or (m_.start() > 0 and w[0].isupper())
                or norm(w) in seen):
            continue
        seen.add(norm(w))
        fix = _typo_fix(cat, w, domain, 86)
        if fix and Levenshtein.distance(norm(w), fix) > 1:
            fix = None
        if fix:
            issues.append(Issue.make(
                "typo", field="Описание", value=w, expected=fix, suggestions=[fix],
                message=f"Возможная опечатка: «{w}» → «{fix}»", severity="warning",
            ))
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
    res.steps.append(NarrowingStep(
        step=1, label="Домен", stage="domain", remaining=n0, removed=0,
        reason=f"Начальный пул КТРУ: домен «{DOMAIN_LABEL.get(domain, domain)}»",
        note=f"{n0} позиций КТРУ в скоупе",
    ))
    if not pool:
        res.issues.append(Issue.make("missing", "Индекс КТРУ пуст — соберите catalog.db", severity="error"))
        return res

    query, typo_issues = correct_query(cat, product, domain, text)
    res.issues.extend(typo_issues)
    # Latin junk («DROP TABLE») must not steer the name match.
    kept_words = [w.strip("'\"«»`") for w in query.split() if not re.fullmatch(r"[A-Za-z]{2,}", w)]
    kept_words = [w for w in kept_words if w]
    if kept_words:
        query = " ".join(kept_words)
    # Enrich only with words shared by several portal cards. One card's extra words
    # («дошколенок» beside «стол») used to pull the code off the product.
    ste = cat.ste_names.get(domain) or []
    if ste and len(norm(query)) >= 3:
        hits = process.extract(norm(query), ste, scorer=fuzz.token_set_ratio, limit=3, score_cutoff=80)
        sets = [tokens(name) - tokens(query) for name, _sc, _i in hits]
        extra = sorted(sets[0].intersection(*sets[1:]))[:3] if len(sets) >= 2 else []
        enriched = query + " " + " ".join(extra) if extra else query
    else:
        enriched = query
    res.query = query

    names, toks = cat.names_for(pool)
    s1 = _scores(query, names, toks)
    synonym_used = False
    if enriched != query:
        s1 = np.maximum(s1, _scores(enriched, names, toks) * 0.9)
    head_q = norm(query).split()[0] if norm(query) else ""
    if domain in ("tools", None) and not power_signal(product, raw):
        hsyn = next((v for k, v in HAND_SYNONYMS.items() if head_q.startswith(k)), None)
        if hsyn is None and head_q.startswith("лобзик"):
            hsyn = "пила ручная"  # в КТРУ нет «лобзика ручного», ближайшая позиция — пила ручная
        if hsyn:
            synonym_used = True
            s1 = np.maximum(s1, _scores(hsyn, names, toks) + 20.0
                            * np.array([n.startswith(hsyn) for n in names], dtype=float))
    if domain in ("tools", None) and power_signal(product, raw):
        head = norm(query).split()[0] if norm(query) else ""
        syn = next((v for k, v in POWER_SYNONYMS.items() if head.startswith(k)), None)
        if syn:
            synonym_used = True
            s1 = np.maximum(s1, _scores(syn + " " + query, names, toks) * 0.95)
        okp = cat.okpd_for(pool)
        s1 = s1 + np.where(np.char.startswith(okp, "28.24"), 20.0,
                           np.where(np.char.startswith(okp, "25.7"), -15.0, 0.0))
        res.power_tool = True
    qws = norm(query).split()
    head0 = qws[0] if qws else ""
    syn = next((v for k, v in HEAD_SYNONYMS.items() if head0.startswith(k)), None)
    if syn and domain in ("clothing", None):
        synonym_used = True
        s1 = np.maximum(s1, _scores(syn + " " + query, names, toks) * 0.95)
    if domain in ("clothing", None) and work_signal(query):
        synonym_used = True
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
            suggestions=["Уточните тип товара (стол/стул/куртка/дрель…)"], severity="warning",
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
        label_cnt: Counter[str] = Counter()
        for c in cands:
            sp = cat.find_spec(c[1], kv.name)
            if sp is None:
                ok_c.append(c)
                continue
            has_spec += 1
            label_cnt[sp.name] += 1
            r = check_value(sp, kv.value, kv.unit, domain, emit=False)
            if r.ok:
                # «Стол» alone must not be promoted to «стол игровой» by a matching size.
                bare = len([w for w in norm(query).split() if len(w) >= 4]) <= 1
                if not bare or _name_words_supported(c[1].name, query):
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
            step=step_no, label=canonical_label(label_cnt, kv.name), stage="char_filter", remaining=len(cands),
            removed=len(bad_c), reason=reason, removed_codes=[c[1].code for c in bad_c[:10]],
            top=[_cand(e, s, m) for s, e, m in sorted(cands, key=lambda x: -x[0])[:8]],
        ))
        step_no += 1

    # variant choice inside a group: allowed values of required characteristics found in the text
    if text_stems is not None:
        for c in cands:
            for sp in c[1].specs.values():
                if sp.required and sp.enums and _enum_from_text(sp, text_stems):
                    c[0] += 6.0
                    c[2].append(sp.name)
    cands.sort(key=lambda x: (-x[0], x[1].code))
    top = cands[0][0]
    group = [(s, e) for s, e, _ in cands if s >= top - GROUP_BAND]
    res.group = group
    res.best = cands[0][1]
    qh = (res.query or query).split()
    bh = norm(res.best.name).split()
    head_ok = False
    if qh and bh:
        a, b = norm(qh[0]), bh[0]
        head_ok = a[:4] == b[:4] or fuzz.ratio(a, b) >= 80
    res.anchored = head_ok or synonym_used
    distinct_names = {e.name for _, e in group}
    other = next((sc for sc, e, _ in cands if e.name != res.best.name), None)
    res.margin = (top - other) if other is not None else 999.0
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
