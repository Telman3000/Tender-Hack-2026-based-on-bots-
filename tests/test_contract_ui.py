import csv
from pathlib import Path

import pytest

from app.config import DB_PATH
from app.engine import CatalogEngine
from app.models import AnalyzeRequest
from app.parser import composite_dimensions, parse_free_text

ROOT = Path(__file__).resolve().parents[1]
needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")

UI_REQUESTS = [
    {"text": "Стол офисный ЛДСП высота 750 мм ширина 1200 мм цвет серый"},
    {"text": "стол офсный дсп высота 1.10 цвет красный"},
    {"text": "Стол письменный 1200х600х750 мм ЛДСП"},
    {"text": "Шкаф для документов ШхГхВ 800x400x1850"},
    {"text": "Стул офисный", "characteristics": [{"name": "Высота", "value": "820", "unit": "мм"}]},
    {"text": "Стеллаж металлический высота 2000 мм"},
    {"text": "Футболка мужская хлопок 100% размер 48"},
    {"text": "Костюм рабочий мужской размер 48-50 рост 170-176"},
    {"text": "Куртка зимняя мужская размер 50"},
    {"text": "Ботинки рабочие кожаные размер 42"},
    {"text": "Молоток слесарный масса 500 г"},
    {"text": "Ключ гаечный 17х19 мм длина 270 мм"},
    {"text": "Дрель ударная мощность 650 Вт"},
    {"text": "Шуруповерт аккумуляторный напряжение 18 В"},
    {"text": "абракадабра непонятная"},
]


@pytest.fixture(scope="module")
def eng():
    e = CatalogEngine()
    yield e
    e.close()


def _qa_requests():
    p = ROOT / "qa" / "cases.csv"
    if not p.exists():
        return []
    return [{"text": r["query"], "domain_hint": r["category"]}
            for r in csv.DictReader(p.open(encoding="utf-8-sig"))]


def test_composite_dimensions_parser():
    kv = composite_dimensions("Стол 1200х600х750 мм")
    assert [(k.name, k.value, k.unit) for k in kv] == [
        ("Ширина", "1200", "мм"), ("Глубина", "600", "мм"), ("Высота", "750", "мм")]
    kv = composite_dimensions("Шкаф ВхШхГ 1850*800*400")
    assert [k.name for k in kv] == ["Высота", "Ширина", "Глубина"]
    # wrench jaw sizes are not dimensions: tools domain keeps no Ширина/Глубина rows
    _, kv = parse_free_text("Ключ гаечный 17х19 мм длина 270 мм", "tools")
    assert not any(k.name in ("Ширина", "Глубина") for k in kv)
    assert any(k.name.lower() == "длина" and k.value == "270" for k in kv)
    _, kv = parse_free_text("Стол размер 1200х750х1200 мм", "furniture")
    assert not any(k.name.lower() == "размер" for k in kv)


@needs_db
def test_char_step_label_is_canonical(eng):
    for text, rows in (
        ("Молоток слесарный масса 500 г", None),
        ("Молоток слесарный", [{"name": "масса", "value": "500", "unit": "г"}]),
        ("Молоток слесарный", [{"name": "МАССА", "value": "0.5", "unit": "кг"}]),
    ):
        r = eng.analyze(AnalyzeRequest(text=text, domain_hint="tools", characteristics=rows))
        steps = [s for s in r.narrowing if s.stage == "char_filter"]
        assert steps and steps[0].label == "Масса молотка", [s.label for s in r.narrowing]
        names = {c.name for c in r.characteristics}
        assert steps[0].label in names


@needs_db
def test_numeric_ktru_rows_have_min_max_unit(eng):
    lacking, total = [], 0
    for q in UI_REQUESTS + _qa_requests():
        r = eng.analyze(AnalyzeRequest(**q))
        for c in r.characteristics:
            if c.source.value != "ktru" or c.allowed:
                continue
            if c.min is None and c.max is None and c.unit is None:
                continue  # free-text KTRU characteristic (not numeric)
            total += 1
            if c.min is None or c.max is None or not c.unit:
                lacking.append((q["text"], c.name, c.min, c.max, c.unit))
    assert total > 0
    assert not lacking, lacking[:10]


@needs_db
def test_status_error_only_for_characteristics(eng):
    r = eng.analyze(AnalyzeRequest(text="абракадабра непонятная"))
    assert r.status == "not_found"
    assert not any(i.severity == "error" for i in r.issues)
    r = eng.analyze(AnalyzeRequest(text="Стол письменный высота 820 кг"))
    assert r.status == "error" and all(i.field for i in r.issues if i.severity == "error")


@needs_db
def test_new_property_is_warning(eng):
    for q in UI_REQUESTS:
        r = eng.analyze(AnalyzeRequest(**q, ) if "characteristics" in q else AnalyzeRequest(
            text=q["text"], characteristics=[{"name": "Противоскользящая ручка", "value": "да"}]))
        for i in r.issues:
            if i.type == "new_property":
                assert i.severity == "warning" and i.kind == i.type


@needs_db
def test_work_suit_is_specodezhda(eng):
    for text in ("Костюм рабочий мужской л08-КБР размер 48-50 рост 170-176 ткань смесовая",
                 "Кастюм рабочий мужкой размер 48-50"):
        r = eng.analyze(AnalyzeRequest(text=text, domain_hint="clothing"))
        assert r.best_ktru and r.best_ktru.code.startswith("14.12.10"), (r.best_ktru.code, r.best_ktru.name)


@needs_db
def test_furniture_composite_maps_to_ktru_names(eng):
    r = eng.analyze(AnalyzeRequest(text="Стол письменный 1200х600х750 мм ЛДСП", domain_hint="furniture"))
    vals = {c.value for c in r.characteristics}
    assert {"1200", "600", "750"} <= vals


@needs_db
def test_required_filled_from_text(eng):
    cases = [
        ("Отвертка аккумуляторная напряжение 3.6 В масса 900 г 1 скорость", "tools", "Тип питания"),
        ("Куртка зимняя Аляска удлиненная черная мужская размер 48-50 рост 170-176 подкладка полиэстер",
         "clothing", "Российский размер"),
    ]
    for text, dom, name in cases:
        r = eng.analyze(AnalyzeRequest(text=text, domain_hint=dom))
        row = [c for c in r.characteristics if c.name == name]
        assert row and row[0].value, (name, [(c.name, c.value) for c in r.characteristics])
        assert not any(i.type == "missing" and i.field == name for i in r.issues)


@needs_db
def test_no_false_typo_for_inflections(eng):
    r = eng.analyze(AnalyzeRequest(text="Стол офисный ЛДСП высота 750 мм", domain_hint="furniture"))
    assert not any(i.type == "typo" for i in r.issues), [i.message for i in r.issues if i.type == "typo"]
    r = eng.analyze(AnalyzeRequest(text="стол офсный дсп", domain_hint="furniture"))
    assert any(i.type == "typo" and i.value == "офсный" for i in r.issues)


@needs_db
def test_single_word_tools_without_hint(eng):
    r = eng.analyze(AnalyzeRequest(text="Дрель"))
    assert r.best_ktru.code.startswith("28.24.1"), r.best_ktru
    r = eng.analyze(AnalyzeRequest(text="Отвертка"))
    assert r.best_ktru.code.startswith(("25.73.3", "28.24.1")), r.best_ktru



@needs_db
def test_ldsp_frame_only_when_explicit():
    e = CatalogEngine()
    r = e.analyze(AnalyzeRequest(text="Стол письменный ЛДСП", domain_hint="furniture"))
    vals = {c.name: c.value for c in r.characteristics}
    assert not vals.get("Вид материала каркаса")
    r = e.analyze(AnalyzeRequest(text="Стол письменный каркас ЛДСП столешница МДФ", domain_hint="furniture"))
    vals = {c.name: c.value for c in r.characteristics}
    assert not vals.get("Вид материала каркаса") or "ЛДСП" in vals["Вид материала каркаса"]
    assert "ЛДСП" not in (vals.get("Вид материала столешницы") or "")


@needs_db
def test_metal_document_cabinet_not_clothes():
    r = CatalogEngine().analyze(AnalyzeRequest(text="Шкаф металлический для документов сварной",
                                               domain_hint="furniture"))
    name = r.best_ktru.name.lower()
    assert "одежд" not in name and "деревян" not in name
