from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter

from rapidfuzz import fuzz

from app.config import DOMAIN_KEYWORDS
from app.models import Issue, KtruCandidate, NarrowingStep, ParsedCharacteristic


def _norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^a-zа-я0-9\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokens(s: str) -> set[str]:
    return {t for t in _norm(s).split() if len(t) > 2}


def score_name(query: str, candidate: str) -> float:
    qn, cn = _norm(query), _norm(candidate)
    if not qn or not cn:
        return 0.0
    t_score = fuzz.token_set_ratio(qn, cn)
    p_score = fuzz.partial_ratio(qn, cn)
    # bonus for shared content words
    qt, ct = _tokens(qn), _tokens(cn)
    overlap = len(qt & ct) / max(1, len(qt))
    return 0.55 * t_score + 0.25 * p_score + 20.0 * overlap


def fetch_ktru_pool(
    conn: sqlite3.Connection,
    domain: str | None,
    limit: int = 4000,
) -> list[sqlite3.Row]:
    if domain:
        rows = conn.execute(
            "SELECT code, name, okpd2, required_json, chars_json FROM ktru WHERE domain=? LIMIT ?",
            (domain, limit),
        ).fetchall()
        if rows:
            return rows
    return conn.execute(
        "SELECT code, name, okpd2, required_json, chars_json FROM ktru LIMIT ?",
        (limit,),
    ).fetchall()


def parse_required(row: sqlite3.Row) -> list[str]:
    raw = row["required_json"]
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    out = []
    for it in data:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict) and it.get("name"):
            out.append(it["name"])
    return out


def narrow_ktru(
    conn: sqlite3.Connection,
    product: str,
    chars: list[ParsedCharacteristic],
    domain: str | None,
) -> tuple[list[NarrowingStep], KtruCandidate | None, list[Issue], list[str]]:
    issues: list[Issue] = []
    steps: list[NarrowingStep] = []
    next_steps: list[str] = []

    pool = fetch_ktru_pool(conn, domain)
    # Enrich query with tokens from closest portal STE names
    portal_tokens = []
    q = _norm(product)
    if domain and len(q) >= 3:
        ste_rows = conn.execute(
            "SELECT name FROM portal_ste WHERE domain=? LIMIT 5000",
            (domain,),
        ).fetchall()
        ste_scored = sorted(
            ((score_name(product, r["name"]), r["name"]) for r in ste_rows),
            key=lambda x: -x[0],
        )[:5]
        for sc, name in ste_scored:
            if sc >= 55:
                portal_tokens.extend(list(_tokens(name))[:5])
    if portal_tokens:
        product = product + " " + " ".join(dict.fromkeys(portal_tokens))

    if not pool:
        # demo fallback if DB empty — should not happen after build_index
        issues.append(
            Issue(
                kind="error",
                message="Индекс КТРУ пуст. Запустите: python -m scripts.build_index",
                suggestion="Соберите data/processed/catalog.db из материалов",
            )
        )
        return steps, None, issues, ["Собрать индекс КТРУ"]

    # Stage 1: domain / name
    scored: list[tuple[float, sqlite3.Row]] = []
    for row in pool:
        s = score_name(product, row["name"])
        # also score against full text of char values
        blob = product + " " + " ".join(f"{c.canonical_name} {c.value}" for c in chars)
        s = max(s, score_name(blob, row["name"]) * 0.9)
        if s >= 35:
            scored.append((s, row))
    scored.sort(key=lambda x: -x[0])
    top_n = scored[:50]

    def to_cand(score: float, row: sqlite3.Row, matched: list[str] | None = None) -> KtruCandidate:
        req = parse_required(row)
        return KtruCandidate(
            code=row["code"],
            name=row["name"],
            okpd2=row["okpd2"],
            score=round(score, 2),
            required_chars=req,
            matched_chars=matched or [],
        )

    steps.append(
        NarrowingStep(
            stage="name_match",
            remaining=len(top_n),
            top=[to_cand(s, r) for s, r in top_n[:8]],
            note=f"После сопоставления названия из {len(pool)} позиций домена осталось {len(top_n)}",
        )
    )

    if not top_n:
        issues.append(
            Issue(
                kind="ambiguous",
                message="Не удалось сопоставить описание ни с одной позицией КТРУ в скоупе",
                suggestion="Уточните тип товара (стол/стул/куртка/дрель…) и ключевые характеристики",
            )
        )
        next_steps.append("Добавьте явное название товара")
        next_steps.append("Укажите 2–3 ключевые характеристики (материал, размер, цвет)")
        return steps, None, issues, next_steps

    # Stage 2: characteristic overlap
    user_names = {c.canonical_name.lower() for c in chars}
    user_values = {_norm(c.value) for c in chars if c.value}

    refined: list[tuple[float, sqlite3.Row, list[str]]] = []
    for score, row in top_n:
        req = [x.lower() for x in parse_required(row)]
        all_chars = req[:]
        try:
            extra = json.loads(row["chars_json"] or "[]")
            for it in extra:
                name = it if isinstance(it, str) else it.get("name")
                if name:
                    all_chars.append(name.lower())
        except Exception:
            pass
        matched = [n for n in user_names if n in set(all_chars)]
        bonus = 8 * len(matched)
        # value tokens in name
        name_toks = _tokens(row["name"])
        val_bonus = 5 * len(user_values & name_toks)
        refined.append((score + bonus + val_bonus, row, matched))

    refined.sort(key=lambda x: -x[0])
    # keep competitive band
    if refined:
        best_score = refined[0][0]
        refined = [x for x in refined if x[0] >= best_score - 25][:25]

    steps.append(
        NarrowingStep(
            stage="char_filter",
            remaining=len(refined),
            top=[to_cand(s, r, m) for s, r, m in refined[:8]],
            note="Сужение по пересечению унифицированных характеристик с карточкой КТРУ",
        )
    )

    best: KtruCandidate | None = None
    if len(refined) == 1 or (
        refined and refined[0][0] - refined[1][0] >= 12 if len(refined) > 1 else True
    ):
        s, r, m = refined[0]
        best = to_cand(s, r, m)
        req = parse_required(r)
        missing = [name for name in req if name.lower() not in user_names]
        for name in missing[:8]:
            issues.append(
                Issue(
                    kind="missing",
                    message=f"Не хватает обязательной характеристики КТРУ: «{name}»",
                    field=name,
                    suggestion=f"Добавьте значение для «{name}»",
                )
            )
            next_steps.append(f"Укажите: {name}")
        steps.append(
            NarrowingStep(
                stage="final",
                remaining=1 if not missing else len(refined),
                top=[best],
                note="Конечный код выбран"
                if not missing
                else "Код-кандидат выбран, но не хватает обязательных характеристик",
            )
        )
    else:
        steps.append(
            NarrowingStep(
                stage="ambiguous",
                remaining=len(refined),
                top=[to_cand(s, r, m) for s, r, m in refined[:8]],
                note="Несколько кодов КТРУ конкурируют — нужно уточнение",
            )
        )
        issues.append(
            Issue(
                kind="ambiguous",
                message=f"Найдено {len(refined)} близких кодов КТРУ — однозначно определить нельзя",
                suggestion="Добавьте отличительные характеристики из топ-кандидатов",
            )
        )
        counter: Counter[str] = Counter()
        for _, r, _ in refined[:10]:
            for name in parse_required(r):
                if name.lower() not in user_names:
                    counter[name] += 1
        for name, _ in counter.most_common(5):
            next_steps.append(f"Уточните: {name}")
        if refined:
            best = to_cand(refined[0][0], refined[0][1], refined[0][2])

    return steps, best, issues, next_steps


def suggest_domain_from_portal(conn: sqlite3.Connection, text: str) -> str | None:
    """Optional: peek STE names for domain hint."""
    low = text.lower()
    for domain, kws in DOMAIN_KEYWORDS.items():
        if any(k in low for k in kws):
            return domain
    row = conn.execute(
        "SELECT domain, name FROM portal_ste WHERE name_norm LIKE ? LIMIT 1",
        (f"%{_norm(text)[:40]}%",),
    ).fetchone()
    return row["domain"] if row else None
