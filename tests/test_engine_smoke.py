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
