from collections import Counter

import pytest

from app.config import DB_PATH
from app.engine import CatalogEngine
from app.models import AnalyzeRequest
from app.morph import flag_answer, words
from app.parser import parse_free_text
from app.spell import Speller

needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")


@pytest.fixture(scope="module")
def eng():
    e = CatalogEngine()
    yield e
    e.close()


def test_speller_layout_typos_and_dictionary_words():
    sp = Speller(Counter({"молоток": 50, "слесарный": 30, "офисный": 40, "стол": 100, "обрезной": 60}))
    text, fixes = sp.fix("vjkjnjr cktcfhysq")
    assert text == "молоток слесарный" and {f.kind for f in fixes} == {"layout"}
    text, fixes = sp.fix("Стол офсный")
    assert text == "Стол офисный" and fixes[0].src == "офсный"
    text, fixes = sp.fix("Круг отрезной")
    assert text == "Круг отрезной" and not fixes


def test_flag_answer():
    assert flag_answer(words("стул с мягким сиденьем"), "Наличие мягкого сидения")[0] == "Да"
    assert flag_answer(words("стул без мягкого сиденья"), "Наличие мягкого сидения")[0] == "Нет"
    assert flag_answer(words("куртка из натуральной кожи"), "Натуральная кожа")[0] == "Да"
    assert flag_answer(words("мягкая обивка, жесткое сиденье"), "Наличие мягкого сидения") is None


def test_material_of_part_and_generic_material():
    _, kv = parse_free_text("Стол письменный, материал столешницы бетон", "furniture")
    assert any(k.name == "Материал столешницы" and k.value == "бетон" for k in kv)
    _, kv = parse_free_text("Плоскогубцы материал губок инструментальная сталь", "tools")
    assert any(k.name == "Материал губок" and k.value == "инструментальная сталь" for k in kv)
    _, kv = parse_free_text("Стол офисный ЛДСП материал плазма", "furniture")
    assert any(k.name == "Материал" and k.value == "плазма" for k in kv)


@needs_db
def test_layout_and_typos_in_whole_text(eng):
    r = eng.analyze(AnalyzeRequest(text="vjkjnjr cktcfhysq"))
    assert r.best_ktru and r.best_ktru.code.startswith("25.73.30.141")
    assert {i.value for i in r.issues if i.type == "typo"} == {"vjkjnjr", "cktcfhysq"}
    r = eng.analyze(AnalyzeRequest(text="Шкав металический для дакументов", domain_hint="furniture"))
    assert {i.value for i in r.issues if i.type == "typo"} == {"Шкав", "металический", "дакументов"}
    assert "деревян" not in r.best_ktru.name.lower()
    r = eng.analyze(AnalyzeRequest(text="Круг отрезной по металлу 150 мм"))
    assert not any(i.type == "typo" for i in r.issues)


@needs_db
def test_value_outside_portal_cards(eng):
    r = eng.analyze(AnalyzeRequest(text="Шкаф для одежды высота 5 мм", domain_hint="furniture"))
    assert r.status == "error"
    assert any(i.type == "mismatch" and i.field == "Высота" and i.severity == "error" for i in r.issues)
    r = eng.analyze(AnalyzeRequest(text="стол офсный дсп высота 1.10 цвет красный", domain_hint="furniture"))
    assert any(i.type == "mismatch" and i.field == "Высота" and i.severity == "warning" for i in r.issues)
    r = eng.analyze(AnalyzeRequest(text="Стол офисный ЛДСП высота 750 мм ширина 1200 мм", domain_hint="furniture"))
    assert not any(i.type == "mismatch" for i in r.issues)


@needs_db
def test_value_not_in_ktru(eng):
    r = eng.analyze(AnalyzeRequest(text="Стол письменный, материал столешницы бетон", domain_hint="furniture"))
    assert r.status == "error"
    issue = next(i for i in r.issues if i.type == "not_allowed")
    assert issue.field == "Вид материала столешницы" and issue.severity == "error" and issue.suggestions
    r = eng.analyze(AnalyzeRequest(text="Стол офисный ЛДСП цвет серый", domain_hint="furniture"))
    assert not [c for c in r.characteristics if c.name == "Материал"]


@needs_db
def test_flag_picks_variant(eng):
    r = eng.analyze(AnalyzeRequest(text="Куртка мужская из натуральной кожи размер 50", domain_hint="clothing"))
    assert r.best_ktru.code == "14.11.10.000-00000005"
    assert {c.name: c.value for c in r.characteristics}.get("Натуральная кожа") == "Да"


@needs_db
def test_question_for_variants(eng):
    r = eng.analyze(AnalyzeRequest(text="Стол письменный", domain_hint="furniture"))
    q = next(i for i in r.issues if i.type == "ambiguous" and i.field)
    assert q.field == "Тип каркаса" and set(q.suggestions) == {"Деревянный", "Металлический"}
    assert not any(i.type == "missing" and i.field == q.field for i in r.issues)
    row = next(c for c in r.characteristics if c.name == q.field)
    assert set(q.suggestions) <= set(row.allowed)
    r = eng.analyze(AnalyzeRequest(text="Стол письменный", domain_hint="furniture",
                                   characteristics=[{"name": "Тип каркаса", "value": "Металлический"}]))
    assert r.best_ktru.code == "31.01.10.000-00000005"
    r = eng.analyze(AnalyzeRequest(text="Шкаф для одежды высота 1800 мм", domain_hint="furniture"))
    names = next(i for i in r.issues if i.type == "ambiguous" and not i.field)
    assert names.value == "Шкаф для одежды" and "Шкаф для одежды деревянный" in names.suggestions
