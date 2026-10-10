from decimal import Decimal

from app.catalog import CharSpec
from app.parser import detect_domain, guess_product_name, parse_free_text
from app.units import canon_unit, convert, guess_unit
from app.validate import _in_range, check_value, sanity_issues


def test_units():
    assert canon_unit("Миллиметр") == "мм"
    assert canon_unit("Литр; кубический дециметр") == "л"
    assert convert(1.1, "м", "мм") == 1100
    assert convert(500, "г", "кг") == 0.5
    assert convert(1, "кг", "мм") is None


def test_range_ok_with_conversion():
    sp = CharSpec(name="Высота", ranges=[(700, 800, "greaterOrEqual", "lessOrEqual")], unit="Миллиметр")
    r = check_value(sp, "75", "см")
    assert r.ok and r.value == "750" and r.unit == "мм"
    assert r.raw_value == "75"


def test_ge_boundary_not_equality():
    """«не менее 60» — оператор ge (Decimal), граница 60 проходит, 59 нет."""
    sp = CharSpec(name="Длина", ranges=[(60, None, "greaterOrEqual", None)], unit="Миллиметр")
    assert check_value(sp, "60", "мм").ok
    assert not check_value(sp, "59", "мм").ok
    assert _in_range(Decimal("60"), 60, None, "greaterOrEqual", None)
    assert not _in_range(Decimal("60"), 60, None, "greaterThan", None)


def test_out_of_range():
    sp = CharSpec(name="Высота", ranges=[(700, 800, None, None)], unit="Миллиметр")
    r = check_value(sp, "1100", "мм")
    assert not r.ok and r.issue.type == "out_of_range" and r.issue.severity == "error"


def test_not_actual_filename_skipped():
    from app.db import is_not_actual_name

    assert is_not_actual_name("nsiKTRUNew_all_not-actual_20261003.xml")
    assert is_not_actual_name("path/all-not-actual_001.xml")
    assert not is_not_actual_name("nsiKTRUNew_all_actual_20261003020003_001.xml")
    assert not is_not_actual_name("all_actual_part.zip")


def test_wrong_unit_dimension():
    sp = CharSpec(name="Высота", ranges=[(700, 800, None, None)], unit="Миллиметр")
    r = check_value(sp, "820", "кг")
    assert not r.ok and r.issue.type == "unit"


def test_bare_number_guess():
    sp = CharSpec(name="Высота", ranges=[(700, 800, None, None)], unit="Миллиметр")
    r = check_value(sp, "75", None)
    assert r.ok and r.issue.type == "unit" and r.issue.severity == "warning"
    assert guess_unit(1.1, "Высота", domain="furniture") == "м"


def test_enum_not_allowed_and_typo():
    sp = CharSpec(name="Материал", enums=["ЛДСП", "МДФ", "Массив древесины"])
    r = check_value(sp, "стекло", None)
    assert not r.ok and r.issue.type == "not_allowed" and len(r.issue.suggestions) <= 3
    assert check_value(sp, "лдсп", None).ok


def test_sanity():
    assert any(i.type == "unit" for i in sanity_issues("Высота", "820", "кг", "furniture"))
    assert any(i.type == "mismatch" for i in sanity_issues("Содержание хлопок", "300", "%", "clothing"))


def test_domain_word_boundaries():
    assert detect_domain("Лампа настольная") is None
    assert detect_domain("Набор, включая провод") is None
    assert detect_domain("Набор музыкальных инструментов") is None
    assert detect_domain("Стол офисный ЛДСП") == "furniture"


def test_head_phrase():
    assert guess_product_name("Стол офисный ЛДСП высота 750 мм цвет серый") == "Стол офисный ЛДСП"
    _, kv = parse_free_text("Футболка хлопок 300% размер 48")
    assert any(k.unit == "%" for k in kv)
