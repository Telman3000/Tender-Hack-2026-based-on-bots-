from __future__ import annotations

import sqlite3

from app.db import connect, db_ready
from app.matcher import narrow_ktru
from app.models import AnalyzeRequest, AnalyzeResponse, Issue
from app.parser import detect_domain, parse_free_text
from app.unify import unify_characteristics


class CatalogEngine:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self.conn = conn or connect()

    def close(self) -> None:
        if self._own_conn:
            self.conn.close()

    def analyze(self, req: AnalyzeRequest) -> AnalyzeResponse:
        if not db_ready():
            return AnalyzeResponse(
                input_text=req.text,
                detected_domain=None,
                product_guess=None,
                characteristics=[],
                issues=[
                    Issue(
                        kind="error",
                        message="База catalog.db не собрана",
                        suggestion="python -m scripts.build_index --materials _materials",
                    )
                ],
                narrowing=[],
                best_ktru=None,
                status="error",
                next_steps=["Собрать индекс из материалов хакатона"],
            )

        domain = detect_domain(req.text, req.domain_hint)
        product, raw = parse_free_text(req.text)

        # First-pass unify without KTRU candidates
        chars, issues = unify_characteristics(self.conn, raw, domain, candidate_codes=None)

        narrowing, best, match_issues, next_steps = narrow_ktru(
            self.conn, product, chars, domain
        )
        issues.extend(match_issues)

        # Second-pass unify against best candidates' char names
        codes = []
        if narrowing:
            for step in narrowing:
                for c in step.top:
                    codes.append(c.code)
        if codes:
            chars2, issues2 = unify_characteristics(
                self.conn, raw, domain, candidate_codes=list(dict.fromkeys(codes))[:20]
            )
            # prefer second pass names
            chars = chars2
            # keep unique issues
            seen = {(i.kind, i.message) for i in issues}
            for i in issues2:
                key = (i.kind, i.message)
                if key not in seen:
                    issues.append(i)
                    seen.add(key)

        status = "ok"
        if any(i.kind == "error" for i in issues):
            status = "error"
        elif any(i.kind in {"missing", "ambiguous"} for i in issues):
            status = "need_more" if any(i.kind == "missing" for i in issues) else "ambiguous"
        elif best is None:
            status = "need_more"

        if not chars:
            issues.append(
                Issue(
                    kind="missing",
                    message="Не удалось выделить характеристики из текста",
                    suggestion="Формат: «Стол офисный ДСП высота 750 мм цвет серый»",
                )
            )
            next_steps.append("Перечислите характеристики явно")
            status = "need_more"

        return AnalyzeResponse(
            input_text=req.text,
            detected_domain=domain,
            product_guess=product,
            characteristics=chars,
            issues=issues,
            narrowing=narrowing,
            best_ktru=best,
            status=status,
            next_steps=list(dict.fromkeys(next_steps))[:10],
            debug={"raw_count": len(raw)},
        )
