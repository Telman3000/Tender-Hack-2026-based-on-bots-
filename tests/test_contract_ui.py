import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import DB_PATH
from app.engine import CatalogEngine
from app.models import AnalyzeRequest, AnalyzeResponse
from app.parser import composite_dimensions, parse_free_text

ROOT = Path(__file__).resolve().parents[1]
FIELDS = set(AnalyzeResponse.model_fields)
HAS_CONTRACT = {"match_status", "search", "checks", "question"} <= FIELDS
needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")
needs_contract = pytest.mark.skipif(not HAS_CONTRACT, reason="app/models.py without match_status/search/checks/question")

TYPO = "Дрэль ударная мощность 0,65 кВт"
QUESTION = "Ключ"
CONFLICT = "Стол письменный высота 750 мм высота 900 мм"
EXTRA = "Кресло офисное обивка ткань цвет черный, экологичность: E1"

MATCH_STATUSES = {"MATCHED", "NEEDS_CLARIFICATION", "INPUT_CONFLICT", "NO_MATCH_IN_SNAPSHOT"}
CARD_STATUSES = {"READY", "INCOMPLETE", "HAS_UNVERIFIED_EXTRAS"}

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
DEMO_REQUESTS = [
    {"text": TYPO, "domain_hint": "tools"},
    {"text": QUESTION, "domain_hint": "tools"},
    {"text": CONFLICT},
    {"text": EXTRA},
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


def as_json(r):
    return r.model_dump(by_alias=True, mode="json")


def ask(eng, text, domain=None, rows=None):
    return as_json(eng.analyze(AnalyzeRequest(text=text, domain_hint=domain, characteristics=rows)))


def span_of(x):
    s = x.get("span") if isinstance(x, dict) else getattr(x, "span", None)
    if s is None:
        return None
    if isinstance(s, (list, tuple)):
        return int(s[0]), int(s[1])
    if isinstance(s, dict):
        return int(s["start"]), int(s["end"])
    return int(s.start), int(s.end)


def card_kind(r):
    v = getattr(r.card_status, "value", r.card_status)
    return {"complete": "ready", "READY": "ready", "HAS_UNVERIFIED_EXTRAS": "ready",
            "incomplete": "incomplete", "invalid": "incomplete", "INCOMPLETE": "incomplete"}[v]


def frontend_fields():
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    return set(re.findall(r"\b(?:data|d|state\.data)\.([a-z_]+)\b", js))


def test_composite_dimensions_parser():
    kv = composite_dimensions("Стол 1200х600х750 мм")
    assert [(k.name, k.value, k.unit) for k in kv] == [
        ("Ширина", "1200", "мм"), ("Глубина", "600", "мм"), ("Высота", "750", "мм")]
    kv = composite_dimensions("Шкаф ВхШхГ 1850*800*400")
    assert [k.name for k in kv] == ["Высота", "Ширина", "Глубина"]
    _, kv = parse_free_text("Ключ гаечный 17х19 мм длина 270 мм", "tools")
    assert not any(k.name in ("Ширина", "Глубина") for k in kv)
    assert any(k.name.lower() == "длина" and k.value == "270" for k in kv)
    _, kv = parse_free_text("Стол размер 1200х750х1200 мм", "furniture")
    assert not any(k.name.lower() == "размер" for k in kv)


@needs_contract
def test_frontend_reads_only_fields_of_the_response():
    used = frontend_fields() - {"detail"}
    assert {"match_status", "card_status", "search", "checks", "question", "characteristics", "input_text"} <= used
    assert used <= FIELDS, sorted(used - FIELDS)


@needs_db
@needs_contract
@pytest.mark.parametrize("q", UI_REQUESTS + DEMO_REQUESTS, ids=lambda q: q["text"][:40])
def test_screen_fields_have_contract_values(eng, q):
    r = ask(eng, q["text"], q.get("domain_hint"), q.get("characteristics"))
    assert r["match_status"] in MATCH_STATUSES
    assert r["card_status"] in CARD_STATUSES
    s = r["search"]
    for k in ("area_size", "checked_count", "compatible_count"):
        assert isinstance(s[k], int) and s[k] >= 0
    assert s["compatible_count"] <= s["area_size"]
    assert s["completeness"] in ("full", "partial")
    for c in r["checks"]:
        assert c["outcome"] in ("PASS", "FAIL", "UNKNOWN")
        if c["outcome"] == "FAIL":
            assert c["code"] and c["reason"]
    failed = {c["code"] for c in r["checks"] if c["outcome"] == "FAIL"}
    assert len(failed) <= s["area_size"] - s["compatible_count"]
    for c in r["characteristics"]:
        assert c["origin"] in ("ktru", "portal", "new")
        sp = span_of(c)
        if sp:
            assert 0 <= sp[0] < sp[1] <= len(q["text"])
    q2 = r["question"]
    if q2 and q2.get("options"):
        assert q2["field"] and 2 <= len(q2["options"]) <= 6


@needs_db
@needs_contract
def test_no_match_only_after_full_area_pass(eng):
    for q in UI_REQUESTS + DEMO_REQUESTS + _qa_requests():
        r = ask(eng, q["text"], q.get("domain_hint"), q.get("characteristics"))
        s = r["search"]
        if r["match_status"] == "NO_MATCH_IN_SNAPSHOT":
            assert s["completeness"] == "full" and s["compatible_count"] == 0, (q["text"], s)
        if r["match_status"] == "MATCHED":
            assert s["completeness"] == "full" and r["best_ktru"], (q["text"], s)


@needs_db
@needs_contract
def test_typo_with_unit(eng):
    r = ask(eng, TYPO, "tools")
    typo = [c for c in r["corrections"] if c["kind"] == "typo"]
    assert typo and typo[0]["from"] == "Дрэль" and typo[0]["to"].lower() == "дрель"
    assert span_of(typo[0]) == (0, 5)
    power = next(c for c in r["characteristics"] if c["name"] == "Мощность")
    assert (power["value"], power["unit"]) == ("650", "Вт")
    sp = span_of(power)
    assert sp and TYPO[sp[0]:sp[1]] == "мощность 0,65 кВт"
    assert power["user_input"]


@needs_db
@needs_contract
def test_answer_appended_to_text_narrows_compatible(eng):
    r = ask(eng, QUESTION, "tools")
    q = r["question"]
    assert r["match_status"] == "NEEDS_CLARIFICATION" and q and q["field"] and q["options"]
    before = r["search"]["compatible_count"]
    option = q["options"][-1]
    r2 = ask(eng, f"{QUESTION}, {q['field']}: {option}", "tools")
    after = r2["search"]["compatible_count"]
    assert after < before
    assert any(c["name"] == q["field"] and c["value"] == option for c in r2["characteristics"])


@needs_db
@needs_contract
def test_conflict_stops_selection(eng):
    r = ask(eng, CONFLICT)
    assert r["match_status"] == "INPUT_CONFLICT"
    assert r["best_ktru"] is None and not r["candidates"]
    assert r["code_status"] == "not_found"
    assert any(i["severity"] == "error" and "INPUT_CONFLICT" in i["message"] for i in r["issues"])
    heights = [c for c in r["characteristics"] if c["name"].lower() == "высота"]
    assert {c["value"] for c in heights} == {"750", "900"}
    assert all(span_of(c) for c in heights)
    r2 = ask(eng, "Стол письменный высота 750 мм")
    assert r2["match_status"] != "INPUT_CONFLICT"


@needs_db
@needs_contract
def test_extra_property_is_new_and_separate(eng):
    r = ask(eng, EXTRA)
    extra = [c for c in r["characteristics"] if c["origin"] == "new"]
    assert [c["name"] for c in extra] == ["Экологичность"]
    assert extra[0]["value"] == "E1" and span_of(extra[0])
    assert r["card_status"] == "HAS_UNVERIFIED_EXTRAS"
    assert any(i["type"] == "new_property" and i["severity"] == "warning" for i in r["issues"])


def test_db_failure_is_visible_to_screen(tmp_path):
    code = (
        "import json\n"
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "with TestClient(app) as c:\n"
        "    h = c.get('/api/health').json()\n"
        "    r = c.post('/api/analyze', json={'text': 'Стол письменный'})\n"
        "    print(json.dumps({'health': h, 'code': r.status_code, 'body': r.json()}, ensure_ascii=False))\n"
    )
    env = {**os.environ, "CATALOG_DB": str(tmp_path / "missing" / "catalog.db")}
    run = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    res = json.loads(run.stdout.strip().splitlines()[-1])
    assert res["health"]["db_ready"] is False
    body = res["body"]
    if res["code"] < 500:
        assert not (body.get("search") or {}).get("area_size")
        assert not body.get("narrowing")
        assert body.get("status") == "error"


def test_repository_has_no_secrets_or_weights():
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, timeout=60)
    except FileNotFoundError:
        pytest.skip("git not installed")
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    files = [f for f in out.stdout.decode("utf-8", "replace").split("\0") if f]
    heavy = re.compile(r"\.(pt|pth|bin|onnx|safetensors|ckpt|gguf|h5|pkl|joblib|db|sqlite3?|zip|xlsx|xml)$", re.I)
    assert not [f for f in files if heavy.search(f)]
    assert not [f for f in files if (ROOT / f).is_file() and (ROOT / f).stat().st_size > 5_000_000]
    assert not [f for f in files if Path(f).name == ".env" or Path(f).name.startswith(".env.") and not f.endswith(".example")]
    secret = re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9]{32,}"
        r"|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|y0_[A-Za-z0-9_-]{30,}|AQVN[A-Za-z0-9_-]{30,}"
    )
    found = []
    for f in files:
        p = ROOT / f
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if secret.search(text):
            found.append(f)
    assert not found


@needs_db
def test_char_step_label_is_canonical(eng):
    for text, rows in (
        ("Молоток слесарный масса 500 г", None),
        ("Молоток слесарный", [{"name": "масса", "value": "500", "unit": "г"}]),
        ("Молоток слесарный", [{"name": "МАССА", "value": "0.5", "unit": "кг"}]),
    ):
        r = eng.analyze(AnalyzeRequest(text=text, domain_hint="tools", characteristics=rows))
        steps = [s for s in r.narrowing if s.label not in ("Домен", "Наименование", "ОКПД2", "Итог")]
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
                continue
            total += 1
            if c.min is None or c.max is None or not c.unit:
                lacking.append((q["text"], c.name, c.min, c.max, c.unit))
    assert total > 0
    assert not lacking, lacking[:10]


@needs_db
def test_status_error_only_for_characteristics(eng):
    r = eng.analyze(AnalyzeRequest(text="абракадабра непонятная"))
    assert r.best_ktru is None and r.code_status == "not_found"
    assert not any(i.severity == "error" for i in r.issues)
    r = eng.analyze(AnalyzeRequest(text="Стол письменный высота 820 кг"))
    assert r.status == "error" and all(i.field for i in r.issues if i.severity == "error")


@needs_db
def test_new_property_is_warning(eng):
    for q in UI_REQUESTS:
        r = eng.analyze(AnalyzeRequest(**q) if "characteristics" in q else AnalyzeRequest(
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
def test_ldsp_frame_only_when_explicit(eng):
    r = eng.analyze(AnalyzeRequest(text="Стол письменный ЛДСП", domain_hint="furniture"))
    vals = {c.name: c.value for c in r.characteristics}
    assert not vals.get("Вид материала каркаса")
    r = eng.analyze(AnalyzeRequest(text="Стол письменный каркас ЛДСП столешница МДФ", domain_hint="furniture"))
    vals = {c.name: c.value for c in r.characteristics}
    assert not vals.get("Вид материала каркаса") or "ЛДСП" in vals["Вид материала каркаса"]
    assert "ЛДСП" not in (vals.get("Вид материала столешницы") or "")


@needs_db
def test_metal_document_cabinet_not_clothes(eng):
    r = eng.analyze(AnalyzeRequest(text="Шкаф металлический для документов сварной", domain_hint="furniture"))
    name = r.best_ktru.name.lower()
    assert "одежд" not in name and "деревян" not in name


@needs_db
@pytest.mark.parametrize("text", [
    "Стол офисный ЛДСП высота 750 мм ширина 1200 мм цвет серый",
    "Стол офисный ЛДСП",
    "Стол письменный ЛДСП 1200х600х750 мм",
])
def test_office_desk_is_writing_desk(eng, text):
    r = eng.analyze(AnalyzeRequest(text=text))
    assert r.best_ktru.name == "Стол письменный"
    vals = {c.name: c.value for c in r.characteristics}
    assert vals.get("Вид материала столешницы") == "ЛДСП"
    assert not vals.get("Вид материала каркаса")


@needs_db
def test_side_table_when_requested(eng):
    r = eng.analyze(AnalyzeRequest(text="Стол приставной ЛДСП"))
    assert r.best_ktru.name == "Стол приставной"


@needs_db
def test_bare_dimension_defaults_to_mm_with_warning(eng):
    r = eng.analyze(AnalyzeRequest(text="Стол письменный высота 750 ширина 1.2"))
    rows = {c.name: c for c in r.characteristics}
    h = next(c for n, c in rows.items() if n.lower().startswith("высота"))
    assert h.unit == "мм" and h.value == "750"
    w = next(c for n, c in rows.items() if n.lower().startswith("ширина"))
    assert w.unit in ("м", "мм") and w.value in ("1.2", "1200")
    assert sum(1 for i in r.issues if i.type == "unit" and i.severity == "warning") >= 2
    assert not any(i.severity == "error" for i in r.issues)


@needs_db
def test_no_duplicate_portal_material_row(eng):
    r = eng.analyze(AnalyzeRequest(text="Стол офисный ЛДСП"))
    ldsp = [c for c in r.characteristics if c.value == "ЛДСП"]
    assert [c.name for c in ldsp] == ["Вид материала столешницы"]


@needs_db
@pytest.mark.parametrize("text", ["Стол офисный ЛДСП высота 750 мм ширина 1200 мм цвет серый",
                                  "Стул офисный", "Шкаф для документов"])
def test_next_steps_match_table(eng, text):
    r = eng.analyze(AnalyzeRequest(text=text))
    rows = {c.name: c.value for c in r.characteristics}
    asked = [s.split(": ", 1)[1] for s in r.next_steps if s.startswith(("Укажите: ", "Уточните: "))]
    assert len(asked) == len(set(asked))
    for n in asked:
        assert n in rows and not rows[n]
    assert not any(s.startswith("Уточните: ") for s in r.next_steps)


@needs_db
def test_code_and_card_status(eng):
    r = eng.analyze(AnalyzeRequest(text="Стол офисный ЛДСП"))
    assert r.code_status == "determined" and card_kind(r) == "incomplete"
    c = r.completeness
    assert c.required_total == sum(1 for x in r.characteristics if x.required)
    assert c.required_filled < c.required_total
    assert r.next_steps and all(d.required for d in r.next_steps_detail if d.text in r.next_steps)
    assert set(r.next_steps) == {d.text for d in r.next_steps_detail if d.required}
    r = eng.analyze(AnalyzeRequest(text="абвгд ёжзий"))
    assert r.code_status == "not_found" and r.best_ktru is None
    r = eng.analyze(AnalyzeRequest(text="Ключ гаечный 170х190 мм длина 27 м"))
    assert card_kind(r) == "incomplete" and any(i.severity == "error" for i in r.issues)


@needs_db
def test_spans_and_corrections(eng):
    text = "Ключ гаечный длина 27 см"
    r = eng.analyze(AnalyzeRequest(text=text))
    rows = [c for c in r.characteristics if c.value and span_of(c)]
    assert rows and all(0 <= span_of(c)[0] < span_of(c)[1] <= len(text) for c in rows)
    kinds = {(x.kind, x.from_, x.to) for x in r.corrections}
    assert any(k == "unit" and "27" in f and "270" in t for k, f, t in kinds) or any(
        c.value == "270" and c.unit == "мм" and "27 см" in (c.user_input or "") for c in r.characteristics), kinds
    for x in r.corrections:
        sp = span_of(x)
        if sp:
            assert text[sp[0]:sp[1]].lower() == x.from_.lower()
    r = eng.analyze(AnalyzeRequest(text="Kurtka zimnyaya muzhskaya"))
    assert any(x.kind == "translit" for x in r.corrections)


def test_correction_serializes_from():
    from app.models import Correction
    d = Correction(kind="unit", from_="27 см", to="270 мм").model_dump(by_alias=True)
    assert d["from"] == "27 см"


@needs_db
@pytest.mark.parametrize("text,value", [
    ("Стул офисный вид материала сиденья пластилин", "пластилин"),
    ("Ключ гаечный тип исполнения квадратный блин", "квадратный блин"),
    ("Молоток тип ювелирный", "ювелирный"),
])
def test_named_value_not_allowed_is_error(eng, text, value):
    r = eng.analyze(AnalyzeRequest(text=text))
    bad = [i for i in r.issues if i.type == "not_allowed"]
    assert bad and bad[0].severity == "error" and 1 <= len(bad[0].suggestions) <= 3
    assert any(c.value == value for c in r.characteristics)
    assert card_kind(r) == "incomplete"


@needs_db
@pytest.mark.parametrize("text,bad", [
    ("Перчатки рабочие размер 25", True), ("Перчатки рабочие размер 9", False),
    ("Стол письменный ширина 5 мм", True), ("Молоток масса 1 г", True),
    ("Стол письменный ширина 1200 мм", False),
])
def test_size_and_lower_limits(eng, text, bad):
    r = eng.analyze(AnalyzeRequest(text=text))
    assert any(i.severity == "error" for i in r.issues) == bad, [i.message for i in r.issues]


def test_size_range_table():
    from app.validate import size_range
    assert size_range("Перчатки трикотажные", "clothing")[:2] == (5, 13)
    assert size_range("Сапоги резиновые", "clothing")[:2] == (15, 50)
    assert size_range("Футболка мужская", "clothing")[:2] == (18, 80)


@needs_db
@pytest.mark.parametrize("text,frm,to", [
    ("Молотак слесарный", "Молотак", "молоток"),
    ("Перчаттки рабочие", "Перчаттки", "перчатки"),
    ("Куртка утепленая мужская", "утепленая", "утепленная"),
])
def test_typo_corrections(eng, text, frm, to):
    r = eng.analyze(AnalyzeRequest(text=text))
    assert any(c.kind == "typo" and c.from_ == frm and c.to == to for c in r.corrections), r.corrections


@needs_db
@pytest.mark.parametrize("text", ["Стол офисный ЛДСП высота 750 мм", "Куртка зимняя мужская размер 50",
                                  "Шуруповерт аккумуляторный 18 В"])
def test_no_false_typos(eng, text):
    assert not any(i.type == "typo" for i in eng.analyze(AnalyzeRequest(text=text)).issues)


@needs_db
def test_error_fix_steps_are_required(eng):
    r = eng.analyze(AnalyzeRequest(text="Ключ гаечный 170х190 мм длина 27 м"))
    assert any(i.severity == "error" for i in r.issues)
    fixes = [d for d in r.next_steps_detail if d.text.startswith("Исправьте")]
    assert fixes and all(d.required for d in fixes)
    assert all(d.text in r.next_steps for d in fixes)


def test_adjective_to_noun_value_match():
    from types import SimpleNamespace
    from app.unify import _match_enum
    sp = SimpleNamespace(enums=["Алюминий", "Дерево", "Металл"])
    assert _match_enum(sp, ["алюминиевый", "профиль"], "алюминиевый профиль") == "Алюминий"
    assert _match_enum(sp, ["деревянный"], "деревянный") == "Дерево"
    assert _match_enum(sp, ["пластилин"], "пластилин") is None


def test_value_runs_until_next_name_or_separator():
    from app.unify import _phrase_words
    ws = _phrase_words("Вид защиты от воды и масел, цвет синий")
    assert [w for w, sg in ws if sg == 0][-1] == "масел"


@needs_db
def test_common_words_are_not_typos(eng):
    r = eng.analyze(AnalyzeRequest(text="Стол письменный ЛДСП, срок поставки 10 дней"))
    assert not any(i.type == "typo" and (i.value or "").lower() == "поставки" for i in r.issues)
