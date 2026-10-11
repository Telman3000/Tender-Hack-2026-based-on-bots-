"""Regression tests for the red-team cases that block the pre-defense."""
import pytest

from app.config import DB_PATH
from app.engine import CatalogEngine
from app.main import decode_csv, parse_names_csv
from app.models import AnalyzeRequest

needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")


@pytest.fixture(scope="module")
def eng():
    return CatalogEngine()


def _an(eng, text, hint=None, chars=None):
    return eng.analyze(AnalyzeRequest(text=text, domain_hint=hint, characteristics=chars))


@needs_db
def test_br052_empty_ktru_is_not_complete(eng):
    r = _an(eng, "Костюм рабочий мужской размер 48-50 рост 170-176", "clothing")
    assert r.best_ktru and r.best_ktru.code.startswith("14.12")
    assert r.card_status != "complete"


@needs_db
def test_br020_hammer_voltage_stays_hand_tool(eng):
    r = _an(eng, "Молоток слесарный 600 г", "tools",
            [{"name": "Напряжение", "value": "18", "unit": "В"}])
    assert r.best_ktru and r.best_ktru.code.startswith("25.73"), (r.best_ktru.code if r.best_ktru else None, r.best_ktru.name if r.best_ktru else None)
    assert not (r.best_ktru and r.best_ktru.code.startswith("28.24"))


@needs_db
def test_br021_screwdriver_rpm_stays_hand_tool(eng):
    r = _an(eng, "Отвертка шлицевая 6 мм", "tools",
            [{"name": "Частота вращения", "value": "3000", "unit": "об/мин"}])
    assert r.best_ktru and not r.best_ktru.code.startswith("28.24")
    assert "шуруповерт" not in r.best_ktru.name.lower()


@needs_db
def test_br001_hint_does_not_override_desk(eng):
    r = _an(eng, "Стол письменный ЛДСП высота 750 мм", "tools")
    assert r.best_ktru and r.best_ktru.code.startswith("31.01.10")


@needs_db
def test_br023_hint_does_not_override_wardrobe(eng):
    r = _an(eng, "Шкаф для одежды металлический 1800х600х2000 мм", "tools")
    assert r.best_ktru and r.best_ktru.code.startswith("31.")


@needs_db
@pytest.mark.parametrize("text", ["Скрипка деревянная для оркестра", "Гитара акустическая"])
def test_br025_br055_foreign_to_tools_is_not_a_random_code(eng, text):
    r = _an(eng, text, "tools")
    assert r.best_ktru is None
    assert r.out_of_scope is True or r.status == "not_found"


@needs_db
def test_br004_new_property_is_not_a_complete_card(eng):
    r = _an(eng, "Костюм рабочий мужской", "clothing", [{"name": "Рост", "value": "170-176"}])
    if any(i.type == "new_property" and (i.field or "").lower().startswith("рост") for i in r.issues):
        assert r.card_status != "complete"


@needs_db
def test_br009_rubber_is_not_gasoline(eng):
    r = _an(eng, "Шпатель STAYER резиновый 150 мм", "tools")
    blob = " ".join(i.message for i in r.issues)
    assert "бензиновый" not in blob


@needs_db
def test_br011_no_absurd_cm_suggestion(eng):
    r = _an(eng, "Стол письменный", "furniture", [{"name": "Высота", "value": "99999", "unit": "мм"}])
    sugg = [s for i in r.issues for s in i.suggestions]
    assert not any("99999 см" in s for s in sugg)


@needs_db
def test_br057_tonne_is_not_silent_kilograms(eng):
    r = _an(eng, "Молоток слесарный масса 0.5 т", "tools")
    mass = [c for c in r.characteristics if "масс" in c.name.lower() and c.value]
    assert mass
    value = float(mass[0].value.replace(",", "."))
    unit = (mass[0].unit or "").lower()
    silent_half_kilo = abs(value - 0.5) < 1e-6 and unit in ("кг", "kg")
    assert not silent_half_kilo
    assert r.card_status == "invalid" or value >= 100


def test_br003_comma_inside_name_stays_one_field():
    items, info = parse_names_csv("name\nСтол, письменный\n")
    assert info["header"] is True
    assert items[0]["text"].replace(",", " ").split()[:2] == ["Стол", "письменный"]


@needs_db
def test_br003_comma_name_is_writing_desk(eng):
    items, _ = parse_names_csv("name\nСтол, письменный\n")
    r = _an(eng, items[0]["text"], "furniture")
    assert r.best_ktru and r.best_ktru.code.startswith("31.01.10")


def test_br082_utf16_roundtrip():
    raw = "name\nСтол письменный\n".encode("utf-16")
    text, enc = decode_csv(raw)
    assert enc == "utf-16"
    items, info = parse_names_csv(text)
    assert info["header"] is True
    assert items == [{"id": 1, "text": "Стол письменный"}]


def test_br083_repeated_name_header_is_not_a_row():
    items, info = parse_names_csv("name,name\nСтол,письменный\n")
    assert info["header"] is True
    assert len(items) == 1
    assert "стол" in items[0]["text"].lower() and "письменный" in items[0]["text"].lower()


@needs_db
def test_br078_br079_foreign_scripts_agree(eng):
    en = _an(eng, "Office desk laminate 1200mm", "furniture")
    zh = _an(eng, "办公桌 1200毫米", "furniture")
    assert en.out_of_scope == zh.out_of_scope
    assert (en.best_ktru is None) == (zh.best_ktru is None) or en.out_of_scope
