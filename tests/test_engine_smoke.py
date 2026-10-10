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
