import csv
import hashlib
from pathlib import Path

from app.catalog import CharSpec, KtruEntry
from app.parser import detect_domain, parse_free_text, parse_text, translit_if_latin
from app.questions import choose_question

_QA = Path(__file__).resolve().parents[1] / "qa"
_LEGACY_SHA = "7d216462018a39029e264c4275a6ce7e29470fc0aed16f3410bf958109dabbe1"


def test_detect_furniture():
    assert detect_domain("Стол офисный ДСП") == "furniture"


def test_detect_tools():
    assert detect_domain("дрель шуруповерт аккумуляторная") == "tools"


def test_parse_pipeline_style():
    product, kvs = parse_free_text(
        "Стол офисный | Материал ДСП | Высота 750 мм | Цвет серый"
    )
    assert "стол" in product.lower()
    names = {k.name.lower() for k in kvs}
    assert "материал" in names or any("дсп" in k.value.lower() for k in kvs)
    assert any(k.name.lower() == "высота" for k in kvs)


def test_parse_free_sentence():
    product, kvs = parse_free_text("стол офисный дсп высота 750 мм цвет серый")
    assert product
    assert any(k.name.lower() == "высота" for k in kvs)
    assert any(k.name.lower() == "цвет" for k in kvs)


def test_translit_strings_stay():
    assert translit_if_latin("Stol ofisnyj LDSP 1200x750 mm") == "стол офисный ЛДСП 1200x750 мм"
    assert translit_if_latin("Kurtka zimnyaya muzhskaya razmer 50") == "куртка зимняя мужская размер 50"
    assert translit_if_latin("Drel udarnaya 650 Vt") == "дрел ударная 650 Вт"


def test_span_points_at_original_phrase():
    text = "стол офисный дсп высота 750 мм цвет серый"
    height = next(kv for kv in parse_text(text).raw if kv.name.lower() == "высота")
    assert text[height.start:height.end] == "высота 750 мм"
    assert height.polarity == "positive"


def test_span_uses_text_before_transliteration():
    text = "molotok massa 500 g"
    parsed = parse_text(text)
    mass = next(kv for kv in parsed.raw if kv.name.lower() == "масса")
    assert text[mass.start:mass.end] == "massa 500 g"
    assert mass.value == "500"
    assert mass.unit == "г"


def test_without_armrests_is_negative_and_not_yes():
    text = "Кресло офисное без подлокотников высота 900 мм"
    parsed = parse_text(text)
    neg = [kv for kv in parsed.raw if kv.polarity == "negative"]
    assert len(neg) == 1
    kv = neg[0]
    assert "подлокотник" in kv.name.lower()
    assert kv.value != "да"
    assert kv.value == "нет"
    assert text[kv.start:kv.end] == "без подлокотников"
    assert all(not (kv2.value == "да" and "подлокотник" in kv2.name.lower()) for kv2 in parsed.raw)


def test_two_products_are_ambiguities_not_one_card():
    text = "нужен стол письменный и стул офисный"
    parsed = parse_text(text)
    assert len(parsed.ambiguities) >= 2
    mentions = " ".join(a.mention.lower() for a in parsed.ambiguities)
    assert "стол" in mentions and "стул" in mentions
    product, raw = parse_free_text(text)
    assert product == ""
    assert raw == []


def _entry(code: str, **specs: list[str]) -> KtruEntry:
    stored = {name.lower(): CharSpec(name=name, enums=list(values)) for name, values in specs.items()}
    return KtruEntry(
        code=code, name=code, okpd2="31.01", domain="furniture",
        name_norm=code, toks=frozenset(), specs=stored,
    )


def test_choose_question_picks_the_field_with_more_values():
    group = [
        _entry("a", Назначение=["письменный", "обеденный", "журнальный"], Цвет=["серый", "черный"]),
        _entry("b", Назначение=["компьютерный"], Цвет=["серый"]),
    ]
    choice = choose_question(group, set(), None)
    assert choice.field == "Назначение"
    assert choice.eliminates >= 1
    assert len(choice.options) <= 6
    assert "компьютерный" in choice.options
    assert "Цвет" not in choice.options or choice.field == "Цвет"


def test_choose_question_skips_filled_and_exhausts():
    group = [
        _entry("a", Назначение=["письменный", "обеденный"], Цвет=["серый", "черный"]),
        _entry("b", Назначение=["компьютерный"], Цвет=["белый"]),
    ]
    choice = choose_question(group, {"Назначение"}, None)
    assert choice.field == "Цвет"
    assert "Назначение" not in (choice.options or [])
    done = choose_question(group, {"Назначение", "Цвет"}, None)
    assert done.field is None
    assert "исчерпано" in done.reason.lower()


def test_legacy_cases_unchanged_and_new_sets_exist():
    rows = list(csv.DictReader((_QA / "cases.csv").open(encoding="utf-8-sig")))
    legacy = [r for r in rows if r.get("set") == "legacy"]
    digest = hashlib.sha256()
    for r in legacy:
        digest.update("|".join([
            r["id"], r["category"], r["type"], r["query"],
            r["expected_code"], r["expected_status"], r["comment"],
        ]).encode())
        digest.update(b"\n")
    assert len(legacy) == 45
    assert digest.hexdigest() == _LEGACY_SHA
    real = [r for r in rows if r.get("set") == "real"]
    perturb = list(csv.DictReader((_QA / "cases_perturb.csv").open(encoding="utf-8-sig")))
    real_groups = {(r["category"], r["group_id"]) for r in real}
    for category in ("clothing", "furniture", "tools"):
        assert sum(1 for r in real if r["category"] == category) >= 15
        assert sum(1 for r in perturb if r["category"] == category) >= 15
    for row in perturb:
        assert row["set"] == "perturb"
        assert (row["category"], row["group_id"]) in real_groups
        assert row["type"] in {"typo", "unit", "missing", "contradiction"}
