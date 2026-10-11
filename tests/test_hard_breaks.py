"""The stress-set failures: typos, two products, conflicts, bounds, foreign text, negation."""
import pytest

from app.config import DB_PATH
from app.engine import CatalogEngine
from app.models import AnalyzeRequest

needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")


@pytest.fixture(scope="module")
def eng():
    return CatalogEngine()


def _an(eng, text, hint=None):
    return eng.analyze(AnalyzeRequest(text=text, domain_hint=hint))


@needs_db
def test_malatok_is_a_hammer_not_a_vise(eng):
    r = _an(eng, "Малаток слесарный масса 500 г")
    assert r.best_ktru and "молот" in r.best_ktru.name.lower()
    assert "тиск" not in r.best_ktru.name.lower()


@needs_db
def test_two_products_keep_the_second_visible(eng):
    r = _an(eng, "Стол письменный высота 750 мм и стул офисный обивка ткань черный")
    assert any(i.type == "two_products" and "стул" in i.message for i in r.issues)
    assert r.card_status != "complete"


@needs_db
def test_two_heights_and_two_masses_conflict(eng):
    desk = _an(eng, "Стол письменный высота 750 мм высота 900 мм ширина 1200 мм")
    hammer = _an(eng, "Молоток слесарный масса 500 г масса 900 г")
    assert desk.status == "error" and any("несколько" in i.message for i in desk.issues)
    assert hammer.status == "error" and hammer.card_status == "invalid"


@needs_db
def test_at_least_is_not_an_exact_height(eng):
    r = _an(eng, "Стол письменный высота не менее 60 см ширина 1200 мм")
    heights = [c for c in r.characteristics if c.name.lower().startswith("высот") and c.value]
    assert heights == []
    assert any(i.type == "negation" and "не менее" in (i.message or "") for i in r.issues)


@needs_db
def test_english_desk_is_not_a_laminator(eng):
    r = _an(eng, "Office desk laminate height 750 mm width 1200 mm")
    assert r.best_ktru and r.best_ktru.name.lower().startswith("стол")
    assert "ламинатор" not in r.best_ktru.name.lower()


@needs_db
def test_copper_pipe_and_wheelchair_are_not_confident_codes(eng):
    pipe = _an(eng, "Труба медная диаметр 15 мм длина 2 м")
    chair = _an(eng, "Кресло-коляска инвалидное ширина сиденья 450 мм")
    assert pipe.best_ktru is None and pipe.out_of_scope
    assert chair.best_ktru is None or "офисн" not in chair.best_ktru.name.lower()
    assert chair.card_status != "complete"


@needs_db
def test_sql_fragment_does_not_become_a_preschool_table(eng):
    r = _an(eng, "Стол'; DROP TABLE ktru; -- высота 750 мм ширина 1200 мм")
    assert r.best_ktru is None or "дошкол" not in r.best_ktru.name.lower()
    assert r.best_ktru and "стол" in r.best_ktru.name.lower()


@needs_db
def test_tiny_jigsaw_mass_is_an_error(eng):
    r = _an(eng, "Электролобзик вес 2.1 г мощность 600 Вт")
    assert r.status == "error"
    assert any(i.severity == "error" and "2.1" in (i.message or "") for i in r.issues)


@needs_db
def test_hand_jigsaw_is_found(eng):
    r = _an(eng, "Лобзик ручной по дереву длина полотна 300 мм")
    assert r.best_ktru and "пил" in r.best_ktru.name.lower()
    assert not r.best_ktru.code.startswith("28.24")


@needs_db
def test_negation_is_not_silent(eng):
    chair = _an(eng, "Кресло офисное без подлокотников обивка ткань цвет черный")
    jacket = _an(eng, "Куртка зимняя мужская черная размер 48 не полиэстер")
    assert any("подлокотник" in (i.message or "") for i in chair.issues)
    assert chair.card_status != "complete"
    assert any("полиэстер" in (i.message or "") for i in jacket.issues)
    assert jacket.card_status != "complete"


def _filled(r):
    return {(c.name.lower(), (c.value or "").lower(), c.unit) for c in r.characteristics if c.value}


@needs_db
def test_paraphrase_keeps_chair_fabric_and_color(eng):
    r = _an(eng, "Офисное кресло, тканевая обивка, чёрный цвет, высота 1080 мм, ширина 650 мм, глубина 450 мм")
    assert r.best_ktru and "кресло" in r.best_ktru.name.lower()
    vals = _filled(r)
    assert any("1080" == v for _, v, _ in vals)
    assert any(v == "черный" for _, v, _ in vals)
    assert any("текстил" in v for _, v, _ in vals)


@needs_db
def test_na_triple_and_word_numbers_and_half_kilo(eng):
    chair = _an(eng, "Черное кресло для офиса 1080 на 650 на 450 мм")
    dims = _filled(chair)
    assert {v for _, v, _ in dims} >= {"1080", "650", "450"}
    desk = _an(eng, "Письменный стол из ламинированной плиты высота семьсот пятьдесят миллиметров ширина 1200 мм")
    assert desk.best_ktru and "письмен" in desk.best_ktru.name.lower()
    assert any(v == "750" for _, v, _ in _filled(desk))
    assert any("лдсп" in v for _, v, _ in _filled(desk))
    hammer = _an(eng, "Молоток для слесарных работ весом полкилограмма")
    assert hammer.best_ktru and "молот" in hammer.best_ktru.name.lower()
    assert any(v in {"0.5", "0,5"} for _, v, _ in _filled(hammer))


@needs_db
def test_silent_mismatches_stay_visible(eng):
    tire = _an(eng, "Шина автомобильная 205/55 R16")
    assert tire.best_ktru is None and tire.out_of_scope
    hammer = _an(eng, "Молоток слесарный 18 В масса 500 г")
    assert hammer.best_ktru and hammer.best_ktru.code.startswith("25.73")
    assert any("18" == v for _, v, _ in _filled(hammer))
    assert hammer.card_status != "complete"
    length = _an(eng, "Молоток слесарный длина 30 кг")
    row = next(c for c in length.characteristics if c.value == "30")
    assert row.unit != "мм"
    assert length.status == "error"
    drill = _an(eng, "Дрель-шуруповерт аккумуляторная мощность 10.8 Вт цвет серый")
    assert any("аккумулятор" in (i.message or "") or "напряжение" in (i.message or "") for i in drill.issues)
    mixed = _an(eng, "Стол pismennyi ЛДСП высота 750 мм ширина 1200 мм")
    assert mixed.best_ktru and "письмен" in mixed.best_ktru.name.lower()
    shirt = _an(eng, "Футболка хлопок 100％ красная размер 48")
    assert any("100" == v for _, v, _ in _filled(shirt))
    suit = _an(eng, "Костюм рабочий мужской размер 48-50 рост 170-176 ткань смесовая")
    shown = " ".join(c.value for c in suit.characteristics if c.value)
    assert "48-50" in shown and "170-176" in shown
