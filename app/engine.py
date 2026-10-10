from __future__ import annotations

import sqlite3
import time
from collections import defaultdict

from app.catalog import Catalog
from app.config import CHAR_ALIASES
from app.db import connect, db_ready, get_meta
from app.matcher import OK_MARGIN, candidates_view, narrow_ktru, _cand
from app.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    CardStatus,
    CharSource,
    Completeness,
    Correction,
    Issue,
    MatchStatus,
    NextStep,
    ParsedCharacteristic,
    ProductMention,
    Question,
    SearchInfo,
    TextSpan,
    derive_legacy_status,
)
from app.units import canon_unit
from app.validate import is_numeric_spec, numeric_view
from app.parser import RawKV, detect_domain, parse_text
from app.questions import choose_question
from app.unify import unify_characteristics


def _step_field(t: str) -> str | None:
    if t.startswith("Укажите: "):
        return t.split(": ", 1)[1]
    if t.startswith("Исправьте «"):
        return t[len("Исправьте «"):].split("»", 1)[0]
    return None


def _find(text: str, frag: str | None) -> TextSpan | None:
    if not frag:
        return None
    i = text.lower().find(frag.lower())
    return TextSpan(start=i, end=i + len(frag)) if i >= 0 else None


def _span_from_raw(r: RawKV) -> TextSpan | None:
    if getattr(r, "start", -1) >= 0 and getattr(r, "end", -1) > r.start:
        return TextSpan(start=r.start, end=r.end)
    return None


def _add_spans(text: str, chars, issues, user_rows: set[str]) -> None:
    for c in chars:
        if c.span is not None:
            continue
        if c.value and (c.raw_name or c.name).lower() not in user_rows:
            c.span = _find(text, c.user_input) or _find(text, c.value)
    for i in issues:
        if i.span is not None:
            continue
        frag = (i.value or "").split(" ")[0] if i.type == "unit" else i.value
        i.span = _find(text, frag)
        if i.span is None and i.field:
            i.span = _find(text, i.field)


def _corrections(orig: str, text: str, issues, conv) -> list[Correction]:
    out: list[Correction] = []
    if text != orig:
        out.append(Correction(field="Наименование", kind="translit", from_=orig, to=text,
                              span=TextSpan(start=0, end=len(orig))))
    for i in issues:
        if i.type == "typo" and i.value and i.expected and i.value != orig:
            kind = "typo" if i.field in ("Наименование", "Описание") else "autofix"
            out.append(Correction(field=i.field, kind=kind, from_=i.value, to=i.expected,
                                  span=_find(orig, i.value)))
        elif i.type == "unit" and i.severity == "warning" and i.value and i.suggestions:
            out.append(Correction(field=i.field, kind="unit", from_=i.value, to=i.suggestions[0],
                                  span=_find(orig, i.value)))
    for kind, field, frm, to in conv:
        out.append(Correction(field=field, kind=kind, from_=frm, to=to, span=_find(orig, frm)))
    return out


def _detect_input_conflict(raw: list[RawKV], cat: Catalog, best) -> tuple[bool, list[Issue]]:
    by_key: dict[str, list[RawKV]] = defaultdict(list)
    for r in raw:
        if not r.value:
            continue
        if getattr(r, "polarity", "positive") == "negative":
            continue
        key = cat.find_spec(best, r.name).name.lower() if best is not None and cat.find_spec(best, r.name) else (
            CHAR_ALIASES.get(r.name.strip().lower(), r.name.strip()).lower()
        )
        by_key[key].append(r)
    issues: list[Issue] = []
    conflict = False
    for _key, rows in by_key.items():
        vals = {(r.value.strip().lower(), (r.unit or "").strip().lower()) for r in rows}
        if len(vals) > 1:
            conflict = True
            shown = ", ".join(f"«{r.value}{(' ' + r.unit) if r.unit else ''}»" for r in rows[:3])
            issues.append(Issue.make(
                "mismatch", field=rows[0].name, value=rows[0].value,
                message=f"INPUT_CONFLICT: для «{rows[0].name}» заданы противоречивые значения: {shown}",
                severity="error",
            ))
    return conflict, issues


def _to_question(choice) -> Question | None:
    if choice is None:
        return None
    return Question(
        field=choice.field,
        reason=choice.reason or "",
        options=list(choice.options or [])[:6],
        eliminates=int(getattr(choice, "eliminates", 0) or 0),
    )


class CatalogEngine:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self.conn = conn or connect()
        self.catalog: Catalog | None = None
        self.snapshot_id: str | None = None
        if db_ready():
            t = time.perf_counter()
            self.catalog = Catalog(self.conn)
            sid = get_meta(self.conn, "snapshot_id")
            if isinstance(sid, str):
                self.snapshot_id = sid.strip('"') if sid.startswith('"') else sid
            self.load_ms = round((time.perf_counter() - t) * 1000)

    def close(self) -> None:
        if self._own_conn:
            self.conn.close()

    @staticmethod
    def _merge(raw: list[RawKV], req: AnalyzeRequest) -> tuple[list[RawKV], set[str]]:
        if not req.characteristics:
            return raw, set()
        given = {c.name.strip().lower(): c for c in req.characteristics if c.name.strip()}
        merged = [r for r in raw if r.name.lower() not in given]
        for c in req.characteristics:
            if c.name.strip():
                merged.append(RawKV(
                    name=c.name.strip(), value=(c.value or "").strip(), unit=c.unit or None,
                ))
        return merged, set(given)

    def _next_steps(self, nr, chars, issues) -> list[str]:
        filled = {c.name for c in chars if c.value}
        table = {c.name for c in chars}
        out: list[str] = []
        asked: set[str] = set()
        for st in nr.next_steps:
            if st.startswith("Уточните: "):
                n = st.split(": ", 1)[1]
                sp = self.catalog.find_spec(nr.best, n) if nr.best is not None else None
                n = sp.name if sp is not None else n
                if n in filled or n in asked:
                    continue
                if n not in table:
                    if sp is None:
                        continue
                    lo, hi, nu = numeric_view(sp, None) if is_numeric_spec(sp) else (
                        None, None, canon_unit(sp.unit) or sp.unit)
                    chars.append(ParsedCharacteristic(
                        name=sp.name, raw_name="", canonical_name=sp.name, value="",
                        unit=nu, min=lo, max=hi, source=CharSource.KTRU, required=sp.required,
                        allowed=sp.allowed_enums(), confidence=0.0,
                        notes="Отличительная характеристика группы вариаций КТРУ",
                    ))
                    table.add(sp.name)
                asked.add(n)
                out.append(f"Укажите: {n}")
            elif st not in out:
                out.append(st)
        for i in issues:
            if i.type == "missing" and i.field and i.field not in filled and i.field not in asked:
                asked.add(i.field)
                out.append(f"Укажите: {i.field}")
        return out

    def _canon_key(self, name: str, best) -> str:
        sp = self.catalog.find_spec(best, name) if best is not None else None
        if sp is not None:
            return sp.name.lower()
        return CHAR_ALIASES.get(name.strip().lower(), name.strip()).lower()

    def _dedupe_by_canonical(self, raw: list[RawKV], user_rows: set[str], best) -> list[RawKV]:
        user_items = [r for r in raw if r.name.lower() in user_rows]
        keys = {self._canon_key(r.name, best) for r in user_items}
        text_items = [r for r in raw if r.name.lower() not in user_rows
                      and self._canon_key(r.name, best) not in keys]
        return text_items + user_items

    def analyze(self, req: AnalyzeRequest) -> AnalyzeResponse:
        t0 = time.perf_counter()
        empty_search = SearchInfo(snapshot_id=self.snapshot_id)
        if self.catalog is None:
            return AnalyzeResponse(
                input_text=req.text, detected_domain=None, product_guess=None,
                characteristics=[], narrowing=[], best_ktru=None,
                match_status=MatchStatus.NO_MATCH_IN_SNAPSHOT,
                card_status=CardStatus.INCOMPLETE,
                search=empty_search,
                status="error",
                issues=[Issue.make("missing", "База catalog.db не собрана", severity="error",
                                   suggestions=["python -m scripts.build_index --materials <папка материалов>"])],
                next_steps=["Собрать индекс из материалов хакатона"],
            )

        # Offsets in RawKV refer to req.text (parse_text handles transliteration internally)
        domain = detect_domain(req.text, req.domain_hint)
        parsed = parse_text(req.text, domain)

        # Several products in one line → no code selection
        if parsed.ambiguities:
            mentions = [
                ProductMention(mention=a.mention, start=a.start, end=a.end, reason=a.reason)
                for a in parsed.ambiguities
            ]
            return AnalyzeResponse(
                input_text=req.text,
                detected_domain=domain,
                product_guess=None,
                characteristics=[],
                issues=[Issue.make(
                    "ambiguous",
                    "В описании несколько товаров — уточните, какой анализировать",
                    severity="warning",
                    suggestions=[a.mention for a in parsed.ambiguities[:3]],
                )],
                narrowing=[],
                best_ktru=None,
                match_status=MatchStatus.NEEDS_CLARIFICATION,
                card_status=CardStatus.INCOMPLETE,
                search=SearchInfo(snapshot_id=self.snapshot_id, domain=domain),
                ambiguities=mentions,
                status="ambiguous",
                code_status="ambiguous",
                next_steps=["Укажите один товар в запросе"],
                debug={
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "search": {"shortlist": [], "snapshot_id": self.snapshot_id},
                    "ambiguities": [m.model_dump() for m in mentions],
                },
            )

        product = parsed.product
        raw = list(parsed.raw)
        raw, user_rows = self._merge(raw, req)
        filled = [r for r in raw if r.value]

        conflict, conflict_issues = _detect_input_conflict(filled, self.catalog, None)
        nr = narrow_ktru(
            self.catalog, product, filled, domain,
            domain_detected=domain is not None, text=req.text,
        )
        if req.characteristics and nr.best is not None:
            raw = self._dedupe_by_canonical(raw, user_rows, nr.best)
            filled = [r for r in raw if r.value]
            conflict, conflict_issues = _detect_input_conflict(filled, self.catalog, nr.best)

        issues = list(nr.issues) + conflict_issues
        chars, char_issues = unify_characteristics(
            self.catalog, raw, domain, None if conflict else nr.best, user_rows, req.text,
        )
        issues.extend(char_issues)

        # Prefer spans from parser RawKV
        by_name = {(r.name.lower(), (r.value or "").lower()): r for r in raw}
        for c in chars:
            key = ((c.raw_name or c.name).lower(), (c.value or "").lower())
            r0 = by_name.get(key)
            if r0 is not None:
                sp = _span_from_raw(r0)
                if sp is not None:
                    c.span = sp
                if getattr(r0, "polarity", None) == "negative":
                    c.polarity = "negative"

        has_new = any(c.origin == "new" or c.source == CharSource.NEW for c in chars if c.value)
        missing_required = any(c.required and not c.value for c in chars)
        has_error = any(i.severity == "error" for i in issues)
        distinct = nr.distinct_name_count or (
            len({e.name for _, e in nr.group}) if nr.group else 0
        )

        if conflict:
            match_status = MatchStatus.INPUT_CONFLICT
            best = None
            group_for_q: list = []
        elif nr.compatible_count == 0 and nr.area_pass_done and nr.completeness == "full":
            match_status = MatchStatus.NO_MATCH_IN_SNAPSHOT
            best = None
            group_for_q = []
        elif (
            nr.completeness == "full"
            and distinct == 1
            and nr.best is not None
            and not missing_required
            and not has_error
            and filled
            and nr.margin >= OK_MARGIN
        ):
            match_status = MatchStatus.MATCHED
            best = nr.best
            group_for_q = nr.group
        elif nr.best is None and nr.compatible_count == 0:
            match_status = MatchStatus.NO_MATCH_IN_SNAPSHOT
            best = None
            group_for_q = []
        else:
            match_status = MatchStatus.NEEDS_CLARIFICATION
            best = None if conflict else nr.best
            group_for_q = [] if conflict else nr.group

        if match_status == MatchStatus.MATCHED and (nr.completeness != "full" or distinct != 1):
            match_status = MatchStatus.NEEDS_CLARIFICATION

        if missing_required or not filled:
            card_status = CardStatus.INCOMPLETE
        elif has_new and not has_error:
            card_status = CardStatus.HAS_UNVERIFIED_EXTRAS
        elif has_error:
            card_status = CardStatus.INCOMPLETE
        else:
            card_status = CardStatus.READY

        if match_status == MatchStatus.INPUT_CONFLICT:
            best = None
            group_for_q = []

        next_steps = self._next_steps(nr, chars, issues)
        for i in issues:
            if i.severity == "error" and i.field:
                next_steps.append(
                    f"Исправьте «{i.field}»" + (f": {i.suggestions[0]}" if i.suggestions else "")
                )
        if not filled:
            issues.append(Issue.make(
                "missing", "Не удалось выделить характеристики из текста", severity="warning",
                suggestions=["Формат: «Стол офисный ЛДСП высота 750 мм цвет серый»"],
            ))

        status = derive_legacy_status(match_status, card_status, distinct if distinct else 1)
        hard_error = any(
            i.severity == "error" and i.type in ("unit", "out_of_range", "not_allowed", "mismatch")
            for i in issues
        )
        if match_status == MatchStatus.NO_MATCH_IN_SNAPSHOT:
            status = "not_found"
        elif match_status == MatchStatus.INPUT_CONFLICT or hard_error:
            status = "error"
        elif match_status == MatchStatus.NEEDS_CLARIFICATION and distinct > 1:
            status = "ambiguous"
            if not any(i.type == "ambiguous" for i in issues):
                issues.append(Issue.make(
                    "ambiguous", severity="warning",
                    message=f"Отрыв лучшего кода от следующего ({nr.margin:.1f}) мал — проверьте кандидатов",
                    suggestions=["Добавьте отличительные характеристики"],
                ))
        elif match_status == MatchStatus.NEEDS_CLARIFICATION and (not filled or missing_required):
            status = "need_more"

        next_steps = list(dict.fromkeys(next_steps))[:10]
        req_fields = {c.name for c in chars if c.required}
        detail = [
            NextStep(text=t, field=f, required=(f is None or f in req_fields or t.startswith("Исправьте")))
            for t in next_steps for f in [_step_field(t)]
        ]
        _add_spans(req.text, chars, issues, user_rows)
        corrections = _corrections(req.text, req.text, issues, [])
        req_rows = [c for c in chars if c.required]
        opt_rows = [c for c in chars if not c.required]

        filled_names = {c.name for c in chars if c.value}
        q_choice = choose_question(group_for_q or nr.group, filled_names, self.catalog)
        question = _to_question(q_choice)

        shortlist = list(nr.shortlist_codes or [])
        search = SearchInfo(
            snapshot_id=self.snapshot_id,
            domain=domain,
            area_size=nr.area_size,
            checked_count=nr.checked_count,
            compatible_count=nr.compatible_count,
            completeness="full" if nr.completeness == "full" else "partial",
            shortlist=shortlist,
        )

        if best is None or match_status in (
            MatchStatus.NO_MATCH_IN_SNAPSHOT, MatchStatus.INPUT_CONFLICT,
        ):
            code_status = "not_found"
        elif distinct > 1:
            code_status = "ambiguous"
        else:
            code_status = "determined"

        if match_status == MatchStatus.MATCHED:
            shown: list = []
        elif group_for_q and len({e.name for _, e in group_for_q}) > 1:
            shown = nr.shown[:5]
        elif match_status == MatchStatus.NEEDS_CLARIFICATION and nr.shown:
            shown = nr.shown[:5]
        else:
            shown = []

        cand_src = shown if shown else (
            [(s, e) for s, e in nr.group[:5]]
            if match_status == MatchStatus.NEEDS_CLARIFICATION and nr.group else []
        )

        return AnalyzeResponse(
            code_status=code_status,  # type: ignore[arg-type]
            card_status=card_status,
            match_status=match_status,
            search=search,
            checks=list(nr.checks),
            question=question,
            ambiguities=[],
            completeness=Completeness(
                required_total=len(req_rows),
                required_filled=sum(1 for c in req_rows if c.value),
                optional_total=len(opt_rows),
                optional_filled=sum(1 for c in opt_rows if c.value),
            ),
            corrections=corrections,
            next_steps_detail=detail,
            input_text=req.text,
            detected_domain=domain,
            product_guess=nr.query or product,
            characteristics=chars,
            issues=issues,
            narrowing=nr.steps,
            best_ktru=_cand(best, nr.group[0][0] if nr.group and best else 0.0) if best else None,
            candidates=candidates_view(cand_src),
            status=status,
            next_steps=[d.text for d in detail if d.required],
            debug={
                "raw_count": len(raw),
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
                "snapshot_id": self.snapshot_id,
                "area_size": nr.area_size,
                "compatible_count": nr.compatible_count,
                "search": {
                    "shortlist": shortlist,
                    "snapshot_id": self.snapshot_id,
                    "area_size": nr.area_size,
                    "compatible_count": nr.compatible_count,
                    "completeness": search.completeness,
                },
            },
        )
