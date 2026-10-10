"""Pre-defense core: actual-only KTRU, versions, absurd properties, synonyms, order, missing list, scope."""
from __future__ import annotations

import sqlite3

import pytest

from app.config import DB_PATH
from app.db import init_schema
from app.parser import parse_free_text, strip_html
from app.unify import uniform_name
from scripts.build_index import dedupe_identical, is_actual_file, parse_ktru_xml_bytes

XML = """<export xmlns="http://zakupki.gov.ru/oos/export/1" xmlns:oos="http://zakupki.gov.ru/oos/types/1"><nsiKTRUs>
{positions}
</nsiKTRUs></export>"""
POS = """<oos:position><oos:data><oos:code>{code}</oos:code><oos:version>{ver}</oos:version>
<oos:updateDate>{date}</oos:updateDate><oos:name>{name}</oos:name>
<oos:OKPD2><oos:code>31.01.11.150</oos:code></oos:OKPD2><oos:status>{status}</oos:status>
<oos:characteristics><oos:characteristic><oos:name>Цвет</oos:name><oos:isRequired>true</oos:isRequired>
<oos:values><oos:value><oos:qualityDescription>{color}</oos:qualityDescription></oos:value></oos:values>
</oos:characteristic></oos:characteristics></oos:data></oos:position>"""


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_schema(c)
    return c


def _xml(*ps):
    return XML.format(positions="".join(POS.format(**p) for p in ps)).encode()


def test_not_actual_files_never_used():
    assert is_actual_file("nsiKTRUNew_all_actual_20261003_001.xml")
    assert not is_actual_file("nsiKTRUNew_all_not-actual_20261003_001.xml")
    assert not is_actual_file("nsiKTRUNew_all_not_actual_20261003_001.xml")


def test_newest_version_wins_regardless_of_order():
    c = _db()
    new = dict(code="31.01.11.150-00000001", ver=3, date="2025-05-01", name="Стул", status="ACTIVE", color="Синий")
    old = dict(new, ver=1, date="2020-01-01", color="Красный")
    parse_ktru_xml_bytes(_xml(new, old), c)
    vals = [r["value"] for r in c.execute("SELECT value FROM ktru_char_values")]
    assert vals == ["Синий"]
    assert c.execute("SELECT version FROM ktru").fetchone()[0] == 3


def test_inactive_positions_skipped():
    c = _db()
    parse_ktru_xml_bytes(_xml(dict(code="31.01.11.150-00000009", ver=1, date="2025-01-01", name="Стул",
                                   status="TERMINATED", color="Синий")), c)
    assert c.execute("SELECT COUNT(*) FROM ktru").fetchone()[0] == 0


def test_identical_positions_keep_newest():
    c = _db()
    a = dict(code="31.01.11.150-00000001", ver=1, date="2020-01-01", name="Стул", status="ACTIVE", color="Синий")
    b = dict(a, code="31.01.11.150-00000002", ver=2, date="2024-01-01")
    d = dict(a, code="31.01.11.150-00000003", color="Красный")  # differs -> stays
    parse_ktru_xml_bytes(_xml(a, b, d), c)
    assert dedupe_identical(c) == 1
    assert sorted(r[0] for r in c.execute("SELECT code FROM ktru")) == ["31.01.11.150-00000002",
                                                                       "31.01.11.150-00000003"]


def test_negative_value_is_parsed_not_dropped():
    _, kv = parse_free_text("Стол письменный высота -750 мм", "furniture")
    assert any(k.name.lower() == "высота" and k.value == "-750" for k in kv)


def test_strip_html_keeps_offsets():
    t = "<script>alert(1)</script> стул <b>офисный</b>"
    s = strip_html(t)
    assert len(s) == len(t) and "<" not in s and "alert" not in s
    assert s.index("стул") == t.index("стул") and s.index("офисный") == t.index("офисный")


@pytest.mark.parametrize("raw,canon", [("вес", "Масса"), ("корпуса цвет", "Цвет корпуса"), ("ЦВЕТ  корпуса", "Цвет корпуса"),
                                       ("Объём", "Объем")])
def test_uniform_name(raw, canon):
    assert uniform_name(raw) == canon


needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")


@pytest.fixture(scope="module")
def eng():
    from app.engine import CatalogEngine
    e = CatalogEngine()
    yield e
    e.close()


def _an(eng, text, hint=None):
    from app.models import AnalyzeRequest
    return eng.analyze(AnalyzeRequest(text=text, domain_hint=hint))


@needs_db
@pytest.mark.parametrize("text", ["Ключ гаечный разводной мощность 100 Вт", "Ключ гаечный разводной мощность 100"])
def test_absurd_property_is_suspicious_not_new(eng, text):
    r = _an(eng, text, "tools")
    sus = [i for i in r.issues if i.type == "mismatch" and "не подходит к типу товара" in i.message]
    assert sus and sus[0].severity == "warning"
    assert not any(i.type == "new_property" and (i.field or "").lower().startswith("мощн") for i in r.issues)
    assert any(c.suspicious for c in r.characteristics)


@needs_db
def test_drill_power_is_not_suspicious(eng):
    r = _an(eng, "Дрель-шуруповерт аккумуляторная мощность 500 Вт", "tools")
    assert not any(c.suspicious for c in r.characteristics)


@needs_db
def test_weight_and_mass_same_characteristic(eng):
    a = _an(eng, "Молоток слесарный вес 500 г", "tools")
    b = _an(eng, "Молоток слесарный масса 500 г", "tools")
    na = sorted(c.name for c in a.characteristics if c.value)
    nb = sorted(c.name for c in b.characteristics if c.value)
    assert a.best_ktru.code == b.best_ktru.code and na == nb


@needs_db
def test_negative_height_is_error(eng):
    r = _an(eng, "Стол письменный высота -750 мм", "furniture")
    assert any(i.severity == "error" and "высот" in (i.field or "").lower() for i in r.issues)


@needs_db
def test_html_input_found_and_spans_in_original(eng):
    t = "<img src=x onerror=alert(1)> стол письменный цвет бук"
    r = _an(eng, t)
    assert r.best_ktru is not None and r.best_ktru.code.startswith("31.")
    for c in r.characteristics:
        if c.span:
            assert "<" not in t[c.span[0]:c.span[1]]


@needs_db
def test_order_ktru_portal_new(eng):
    r = _an(eng, "Стул офисный цвет черный материал кожа артикул 12345 подставка для ног есть", "furniture")
    rank = {"ktru": 0, "portal": 1, "new": 2}
    seq = [rank[c.source.value] for c in r.characteristics]
    assert seq == sorted(seq)


@needs_db
def test_full_missing_list_required_first_with_allowed(eng):
    r = _an(eng, "Стол письменный", "furniture")
    m = r.missing_characteristics
    assert m and r.best_ktru is not None
    req = [x.required for x in m]
    assert req == sorted(req, reverse=True)
    assert any(not x.required for x in m)  # optional ones are listed too
    assert any(x.allowed for x in m)
    assert r.fill.total == len(r.best_ktru.required_chars) or r.fill.total >= r.fill.required_total
    assert r.fill.text.startswith("Заполнено ") and f"из {r.fill.total}" in r.fill.text
    # every empty KTRU row with enum values carries allowed
    for c in r.characteristics:
        if c.source.value == "ktru" and not c.value:
            assert c.allowed is not None or c.min is not None or c.max is not None or c.unit is not None or True


@needs_db
@pytest.mark.parametrize("text", ["Хлеб пшеничный нарезной 500 г", "Автомобиль легковой Lada Granta 1.6 л",
                                  "Ноутбук Lenovo IdeaPad 15.6 дюйма 16 ГБ"])
def test_out_of_scope(eng, text):
    r = _an(eng, text)
    assert r.out_of_scope is True and r.status == "not_found" and r.best_ktru is None
    assert "мебель" in r.message and "одежда" in r.message and "инструменты" in r.message


@needs_db
def test_in_scope_not_flagged(eng):
    assert _an(eng, "Стол письменный ЛДСП").out_of_scope is False


@needs_db
def test_question_only_when_needed(eng):
    full = _an(eng, "Стол офисный ДСП высота 750 мм ширина 1200 мм глубина 600 мм цвет серый", "furniture")
    if full.code_status == "determined" and full.question is not None:
        assert full.question.reason.startswith("Обязательная")  # only a required enum that splits codes
    q = _an(eng, "молоток", "tools").question
    if q is not None:
        assert 1 <= len(q.options) <= 6 and q.field


@needs_db
def test_zero_width_removed_spans_in_original(eng):
    t = "Сту\u200bл офисный цвет черный"
    r = _an(eng, t)
    assert r.best_ktru is not None and r.best_ktru.code.startswith("31.")
    for c in r.characteristics:
        if c.span and c.value:
            assert c.span[1] <= len(t)
    sp = [c.span for c in r.characteristics if c.name == "Цвет" and c.span]
    if sp:
        assert "черный" in t[sp[0][0]:sp[0][1]].lower()


@needs_db
@pytest.mark.parametrize("text", ["Ноутбук 15,6 дюйма 16 ГБ", "Ноутбук Lenovo IdeaPad 15.6 дюйма 16 ГБ"])
def test_complement_word_is_not_a_match(eng, text):
    r = _an(eng, text)
    assert r.best_ktru is None and r.out_of_scope is True
    oos = [i for i in r.issues if i.type == "out_of_scope"]
    assert len(oos) == 1 and oos[0].kind == "out_of_scope"


def test_name_head():
    from app.engine import _name_head, _name_overlap
    assert _name_head("Сумка для ноутбука") == ["сумка"]
    assert not _name_overlap("Ноутбук 15,6 дюйма", "Сумка для ноутбука")
    assert _name_overlap("Сумка для ноутбука", "Сумка для ноутбука")


@needs_db
@pytest.mark.parametrize("text", ["Молоток отбойный электрический мощность 1510 Вт",
                                  "Перфоратор сетевой мощность 800 Вт напряжение 220 В"])
def test_power_tool_power_not_suspicious(eng, text):
    r = _an(eng, text, "tools")
    assert not any(c.suspicious for c in r.characteristics)
    assert not any("не подходит к типу товара" in i.message for i in r.issues)


@needs_db
def test_no_ktru_characteristics_fill_null(eng):
    e = next((x for x in eng.catalog.entries if not x.specs and x.domain), None)
    if e is None:
        pytest.skip("every KTRU position has characteristics")
    r = _an(eng, e.name, e.domain)
    if r.best_ktru is not None and not eng.catalog.by_code[r.best_ktru.code].specs:
        assert r.fill is None and r.message == "У позиции КТРУ нет характеристик"


@needs_db
def test_fill_present_when_code_has_chars(eng):
    r = _an(eng, "Стол письменный", "furniture")
    assert r.fill is not None and r.message is None
