from __future__ import annotations

import sqlite3
import time

from app.catalog import Catalog
from app.db import connect, db_ready
from app.matcher import OK_MARGIN, candidates_view, narrow_ktru, _cand
from app.models import AnalyzeRequest, AnalyzeResponse, Issue
from app.parser import RawKV, detect_domain, guess_product_name, parse_free_text, translit_if_latin
from app.unify import unify_characteristics


class CatalogEngine:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self.conn = conn or connect()
        self.catalog: Catalog | None = None
        if db_ready():
            t = time.perf_counter()
            self.catalog = Catalog(self.conn)
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
        text = translit_if_latin(req.text)
        product, raw = parse_free_text(text)
        product = guess_product_name(text) or product
        raw, user_rows = self._merge(raw, req)
        domain = detect_domain(text, req.domain_hint)

        filled = [r for r in raw if r.value]
        nr = narrow_ktru(self.catalog, product, filled, domain, domain_detected=domain is not None)
        issues = list(nr.issues)
        chars, char_issues = unify_characteristics(self.catalog, raw, domain, nr.best, user_rows)
        issues.extend(char_issues)
        next_steps = list(nr.next_steps)
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
        if not filled:
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
