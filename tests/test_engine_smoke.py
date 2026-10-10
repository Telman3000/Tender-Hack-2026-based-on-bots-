from pathlib import Path

import pytest

from app.config import DB_PATH
from app.engine import CatalogEngine
from app.models import AnalyzeRequest


@pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")
def test_analyze_table_case():
    eng = CatalogEngine()
    try:
        res = eng.analyze(
            AnalyzeRequest(
                text="Стол офисный ДСП высота 750 мм цвет серый",
                domain_hint="furniture",
            )
        )
        assert res.product_guess
        assert res.detected_domain == "furniture"
        assert isinstance(res.characteristics, list)
        assert res.status in {"ok", "need_more", "ambiguous"}
    finally:
        eng.close()


@pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")
def test_analyze_incomplete():
    eng = CatalogEngine()
    try:
        res = eng.analyze(AnalyzeRequest(text="молоток", domain_hint="tools"))
        assert res.status in {"ok", "need_more", "ambiguous"}
        # incomplete input should usually ask for more OR still propose candidates
        assert res.narrowing or res.issues
        # Person-1: area_size = полный домен «инструменты», не короткий список по имени
        tools_n = len(eng.catalog.pool("tools"))
        assert res.search.area_size == tools_n
        assert res.search.area_size > 80  # not the short-list cap
        assert res.search.completeness in {"full", "partial"}
        assert res.match_status is not None
        assert res.question is None or res.question.field
    finally:
        eng.close()


@pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")
def test_contract_and_errors_block_ok():
    eng = CatalogEngine()
    try:
        res = eng.analyze(AnalyzeRequest(text="Стол письменный высота 820 кг"))
        assert res.status != "ok"
        assert any(i.severity == "error" for i in res.issues)
        assert res.narrowing[0].label == "Домен" and res.narrowing[0].remaining > 0
        assert "elapsed_ms" in res.debug
        res2 = eng.analyze(AnalyzeRequest(
            text="Стол письменный",
            characteristics=[{"name": "Высота", "value": "750", "unit": "мм"},
                             {"name": "Моя доп. строка", "value": ""}],
        ))
        names = {c.name for c in res2.characteristics} | {c.raw_name for c in res2.characteristics}
        assert "Моя доп. строка" in names
        for c in res2.characteristics:
            assert c.allowed is None or isinstance(c.allowed, list)
    finally:
        eng.close()


def test_domain_hint_validation():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        assert c.post("/api/analyze", json={"text": "стол", "domain_hint": "cars"}).status_code == 422
        assert c.post("/api/analyze", json={"text": "стол", "domain_hint": ""}).status_code in (200, 503)


@pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")
def test_status_precedence():
    eng = CatalogEngine()
    try:
        # required KTRU characteristics left empty -> need_more, never ok
        r = eng.analyze(AnalyzeRequest(text="Стол письменный ЛДСП", domain_hint="furniture"))
        if any(c.required and not c.value for c in r.characteristics):
            assert r.status == "need_more"
        # every issue carries kind == type
        assert all(i.kind == i.type for i in r.issues)
        assert eng.analyze(AnalyzeRequest(text="Стол письменный высота 820 кг")).status == "error"
    finally:
        eng.close()


@pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")
def test_frontend_row_replaces_text_row_by_canonical_name():
    eng = CatalogEngine()
    try:
        text = "Ключ гаечный 170х190 мм длина 27 м"
        first = eng.analyze(AnalyzeRequest(text=text, domain_hint="tools"))
        assert first.status == "error"
        canon = next(c.name for c in first.characteristics if c.user_input and c.user_input.lower().startswith("длина"))
        for name in (canon, "длина", "Длина"):
            res = eng.analyze(AnalyzeRequest(
                text=text, domain_hint="tools",
                characteristics=[{"name": name, "value": "270", "unit": "мм"}],
            ))
            rows = [c for c in res.characteristics if c.name == canon]
            assert len(rows) == 1, (name, [(c.name, c.value) for c in res.characteristics])
            assert rows[0].value == "270"
            assert not any(i.severity == "error" and i.field in (canon, "длина") for i in res.issues)
    finally:
        eng.close()
