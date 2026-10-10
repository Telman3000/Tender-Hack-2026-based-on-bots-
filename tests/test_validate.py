from app.catalog import CharSpec
from app.parser import detect_domain, guess_product_name, parse_free_text
from app.units import canon_unit, convert, guess_unit
from app.validate import check_value, sanity_issues


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


def test_out_of_range():
    sp = CharSpec(name="Высота", ranges=[(700, 800, None, None)], unit="Миллиметр")
    r = check_value(sp, "1100", "мм")
    assert not r.ok and r.issue.type == "out_of_range" and r.issue.severity == "error"


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
