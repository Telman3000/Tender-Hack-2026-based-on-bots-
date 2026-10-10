from __future__ import annotations

import re
import sqlite3
import time

from app.catalog import Catalog, KtruEntry, norm
from app.config import CHAR_ALIASES
from app.db import connect, db_ready
from app.matcher import OK_MARGIN, candidates_view, narrow_ktru, variant_question, _cand
from app.models import AnalyzeRequest, AnalyzeResponse, CharSource, Issue, ParsedCharacteristic
from app.morph import STOP
from app.parser import RawKV, detect_domain, guess_product_name, parse_free_text, translit_if_latin
from app.spell import Speller
from app.unify import unify_characteristics
from app.validate import typical_issue

_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")


class CatalogEngine:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self.conn = conn or connect()
        self.catalog: Catalog | None = None
        self.speller: Speller | None = None
        if db_ready():
            t = time.perf_counter()
            self.catalog = Catalog(self.conn)
            self.speller = Speller(self.catalog.word_freq())
            self.load_ms = round((time.perf_counter() - t) * 1000)

    def close(self) -> None:
        if self._own_conn:
            self.conn.close()

    @staticmethod
    def _merge(raw: list[RawKV], req: AnalyzeRequest) -> tuple[list[RawKV], set[str]]:
        """Rows sent by the UI override parsed ones (by name) and are always echoed back."""
        if not req.characteristics:
            return raw, set()
        given = {c.name.strip().lower(): c for c in req.characteristics if c.name.strip()}
        merged = [r for r in raw if r.name.lower() not in given]
        for c in req.characteristics:
            if c.name.strip():
                merged.append(RawKV(name=c.name.strip(), value=(c.value or "").strip(), unit=c.unit or None))
        return merged, set(given)

    def _canon_key(self, name: str, best) -> str:
        sp = self.catalog.find_spec(best, name) if best is not None else None
        if sp is not None:
            return sp.name.lower()
        return CHAR_ALIASES.get(name.strip().lower(), name.strip()).lower()

    def _dedupe_by_canonical(self, raw: list[RawKV], user_rows: set[str], best) -> list[RawKV]:
        """A frontend row replaces any text-parsed row with the same canonical name."""
        user_items = [r for r in raw if r.name.lower() in user_rows]
        keys = {self._canon_key(r.name, best) for r in user_items}
        text_items = [r for r in raw if r.name.lower() not in user_rows
                      and self._canon_key(r.name, best) not in keys]
        return text_items + user_items

    def _spellcheck(self, src: str) -> tuple[str, list[Issue]]:
        text, fixes = self.speller.fix(src)
        latin = translit_if_latin(src)
        layout = sum(f.kind == "layout" for f in fixes)
        if latin != src and layout * 2 < len(_LATIN_WORD.findall(src)):
            text, _ = self.speller.fix(latin)
            return text, [Issue.make(
                "typo", value=src, expected=text, suggestions=[text], severity="warning",
                message=f"Описание набрано латиницей — распознано как «{text}». Проверьте и введите кириллицей",
            )]
        issues = []
        for f in fixes:
            what = "Текст в английской раскладке" if f.kind == "layout" else "Возможная опечатка"
            issues.append(Issue.make(
                "typo", value=f.src, expected=f.dst, suggestions=[f.dst], severity="warning",
                message=f"{what}: «{f.src}» → «{f.dst}»",
            ))
        return text, issues

    def _portal_check(
        self, chars: list[ParsedCharacteristic], issues: list[Issue], best: KtruEntry | None, query: list[str],
    ) -> list[Issue]:
        if not query:
            return []
        flagged = {(i.field or "").lower() for i in issues if i.type in ("unit", "mismatch", "out_of_range", "not_allowed")}
        out = []
        for c in chars:
            if not c.value or {c.name.lower(), c.raw_name.lower()} & flagged:
                continue
            sp = self.catalog.find_spec(best, c.name) if best is not None and c.source == CharSource.KTRU else None
            if sp is not None and (sp.enums or None not in sp.bounds()):
                continue
            unit, issue = typical_issue(c.name, c.value, c.unit, self.catalog.typical(query, c.name), query[0])
            if issue:
                c.unit = c.unit or unit
                out.append(issue)
        return out

    def analyze(self, req: AnalyzeRequest) -> AnalyzeResponse:
        t0 = time.perf_counter()
        if self.catalog is None:
            return AnalyzeResponse(
                input_text=req.text, detected_domain=None, product_guess=None,
                characteristics=[], narrowing=[], best_ktru=None, status="error",
                issues=[Issue.make("missing", "База catalog.db не собрана", severity="error",
                                   suggestions=["python -m scripts.build_index --materials <папка материалов>"])],
                next_steps=["Собрать индекс из материалов хакатона"],
            )
        text, typo_issues = self._spellcheck(req.text)
        domain = detect_domain(text, req.domain_hint)
        product, raw = parse_free_text(text, domain)
        product = guess_product_name(text) or product
        raw, user_rows = self._merge(raw, req)

        filled = [r for r in raw if r.value]
        nr = narrow_ktru(self.catalog, product, filled, domain, domain_detected=domain is not None, text=text)
        if req.characteristics and nr.best is not None:
            raw = self._dedupe_by_canonical(raw, user_rows, nr.best)
            filled = [r for r in raw if r.value]
        issues = typo_issues + list(nr.issues)
        variants = [e for _, e in nr.group if nr.best is not None and e.name == nr.best.name]
        chars, char_issues = unify_characteristics(self.catalog, raw, domain, nr.best, user_rows, text, variants)
        issues.extend(char_issues)
        query = [w for w in norm(nr.query or product).split() if w not in STOP and not w.isdigit()]
        issues.extend(self._portal_check(chars, issues, nr.best, query))
        for i in issues:
            if i.type == "ambiguous" and i.value:
                for t in typo_issues:
                    i.value = i.value.replace(t.expected or t.value, t.value)
                if i.value not in req.text:
                    i.value = None
        known = {c.name for c in chars if c.value}
        next_steps = [s for s in nr.next_steps if not (s.startswith("Уточните: ") and s[len("Уточните: "):] in known)]
        question = variant_question(self.catalog, nr.best, nr.group, chars, domain) if nr.best else None
        if question:
            field, values, n = question
            issues = [i for i in issues if not (i.type == "missing" and i.field == field)]
            pos = max((k + 1 for k, i in enumerate(issues) if i.type in ("typo", "ambiguous")), default=0)
            issues.insert(pos, Issue.make(
                "ambiguous", field=field, suggestions=values, severity="warning",
                message=f"Подходящих кодов КТРУ «{nr.best.name}»: {n}. Они различаются характеристикой «{field}» — выберите значение",
            ))
            next_steps = [f"Выберите «{field}»: " + ", ".join(values[:3])] + [s for s in next_steps if s != f"Уточните: {field}"]
        for i in issues:
            if i.type == "missing" and i.field:
                next_steps.append(f"Укажите: {i.field}")
            elif i.severity == "error" and i.field:
                next_steps.append(f"Исправьте «{i.field}»" + (f": {i.suggestions[0]}" if i.suggestions else ""))

        # precedence: not_found > error > need_more > ambiguous > ok
        missing_required = any(c.required and not c.value for c in chars)
        if nr.best is None:
            status = "not_found"
        elif any(i.severity == "error" for i in issues):
            status = "error"
        elif not filled or missing_required:
            status = "need_more"
        elif (any(i.type in ("ambiguous", "typo") for i in issues) or nr.margin < OK_MARGIN):
            status = "ambiguous"
            if not any(i.type == "ambiguous" for i in issues):
                issues.append(Issue.make(
                    "ambiguous", severity="warning",
                    message=f"Отрыв лучшего кода от следующего ({nr.margin:.1f}) мал — проверьте кандидатов",
                    suggestions=["Добавьте отличительные характеристики"],
                ))
        else:
            status = "ok"
        if not filled and not any(c.value for c in chars):
            issues.append(Issue.make(
                "missing", "Не удалось выделить характеристики из текста", severity="warning",
                suggestions=["Формат: «Стол офисный ЛДСП высота 750 мм цвет серый»"],
            ))

        group = nr.group if len(nr.group) > 1 else []
        return AnalyzeResponse(
            input_text=req.text,
            detected_domain=domain,
            product_guess=nr.query or product,
            characteristics=chars,
            issues=issues,
            narrowing=nr.steps,
            best_ktru=_cand(nr.best, nr.group[0][0] if nr.group else 0.0) if nr.best else None,
            candidates=candidates_view(nr.shown[:5] if len(nr.group) > 1 else []),
            status=status,
            next_steps=list(dict.fromkeys(next_steps))[:10],
            debug={"raw_count": len(raw), "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1)},
        )
