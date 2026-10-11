"""Batch API: JSON items, CSV upload (encodings, delimiters, header), NDJSON stream."""
from __future__ import annotations

import json

import pytest

from app.config import DB_PATH
from app.main import decode_csv, parse_names_csv

needs_db = pytest.mark.skipif(not DB_PATH.exists(), reason="catalog.db not built yet")


def test_decode_utf8_bom_and_cp1251():
    assert decode_csv("\ufeffСтол".encode("utf-8"))[0] == "Стол"
    assert decode_csv("Стол".encode("cp1251")) == ("Стол", "cp1251")


@pytest.mark.parametrize("text,expected", [
    ("Наименование\nСтол письменный\nСтул офисный\n", ["Стол письменный", "Стул офисный"]),
    ("Стол письменный\nСтул офисный, черный\n", ["Стол письменный", "Стул офисный, черный"]),
    ("id;name\n7;Стол письменный\n8;Молоток\n", ["Стол письменный", "Молоток"]),
    ('"Стул офисный, черный"\n"Молоток"\n', ["Стул офисный, черный", "Молоток"]),
    ("Стол;\nМолоток;\n", ["Стол", "Молоток"]),
])
def test_parse_names_csv(text, expected):
    items, _ = parse_names_csv(text)
    assert [i["text"] for i in items] == expected


def test_parse_ids_from_column():
    items, info = parse_names_csv("id;name\n7;Стол\n")
    assert items[0]["id"] == "7" and info["header"]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c


ROWS = ["Стол письменный ЛДСП", "Молоток слесарный", "Хлеб пшеничный 500 г", "", "Куртка зимняя мужская"]


@needs_db
def test_batch_json(client):
    r = client.post("/api/analyze/batch", json={"items": [{"id": i, "text": t} for i, t in enumerate(ROWS)]})
    assert r.status_code == 200
    d = r.json()
    assert [x["id"] for x in d["results"]] == list(range(len(ROWS)))
    assert "error" in d["results"][3]
    assert d["results"][0]["best_ktru"]["code"].startswith("31.")
    assert d["results"][2]["out_of_scope"] is True
    s = d["summary"]
    assert s["total"] == 5 and s["errors"] == 1 and s["by_code_status"]["out_of_scope"] == 1
    assert sum(s["by_code_status"].values()) == 4 and sum(s["by_card_status"].values()) == 4
    single = client.post("/api/analyze", json={"text": ROWS[1]}).json()
    assert single["best_ktru"]["code"] == d["results"][1]["best_ktru"]["code"]


@needs_db
def test_batch_limit(client):
    r = client.post("/api/analyze/batch", json={"items": [{"text": "стол"}] * 501})
    assert r.status_code == 413


@needs_db
def test_batch_stream(client):
    with client.stream("POST", "/api/analyze/batch?stream=1", json={"items": [{"text": t} for t in ROWS[:3]]}) as r:
        assert r.headers["content-type"].startswith("application/x-ndjson")
        lines = [json.loads(x) for x in r.iter_lines() if x]
    assert [x["type"] for x in lines] == ["result"] * 3 + ["summary"]
    assert lines[-1]["summary"]["total"] == 3


@needs_db
@pytest.mark.parametrize("enc", ["utf-8-sig", "cp1251", "utf-8"])
def test_csv_upload(client, enc):
    body = "Наименование\nСтол письменный ЛДСП\nМолоток слесарный\n".encode(enc)
    r = client.post("/api/analyze/csv", files={"file": ("x.csv", body, "text/csv")})
    assert r.status_code == 200
    d = r.json()
    assert d["summary"]["total"] == 2 and d["file"]["header"] is True
    assert d["results"][0]["text"] == "Стол письменный ЛДСП"


@needs_db
def test_csv_stream_accept_header(client):
    body = "Стол письменный\nМолоток\n".encode("utf-8")
    with client.stream("POST", "/api/analyze/csv", files={"file": ("x.csv", body, "text/csv")},
                       headers={"Accept": "application/x-ndjson"}) as r:
        lines = [json.loads(x) for x in r.iter_lines() if x]
    assert len(lines) == 3 and lines[-1]["type"] == "summary" and lines[-1]["file"]["rows"] == 2


@needs_db
def test_csv_empty_422(client):
    r = client.post("/api/analyze/csv", files={"file": ("x.csv", b"\n\n", "text/csv")})
    assert r.status_code == 422


@needs_db
def test_batch_500_identical_rows_under_10s(client):
    """BR-063: 500 одинаковых строк пакета должны уложиться в 10 с и сохранить свои id."""
    items = [{"id": i, "text": "Стол письменный ЛДСП высота 750 мм"} for i in range(500)]
    r = client.post("/api/analyze/batch?stream=1", json={"items": items})
    assert r.status_code == 200
    lines = [json.loads(x) for x in r.text.splitlines() if x]
    results = [ln for ln in lines if ln["type"] == "result"]
    summary = lines[-1]["summary"]
    assert summary["total"] == 500 and summary["elapsed_ms"] < 10000
    assert [ln["id"] for ln in results] == list(range(500))
    assert len({ln["best_ktru"]["code"] for ln in results}) == 1


def test_openapi_advertises_stream_param():
    """The UI enables NDJSON only if /openapi.json lists a `stream` parameter on /api/analyze/batch."""
    from app.main import app
    op = app.openapi()["paths"]["/api/analyze/batch"]["post"]
    assert any(p["name"] == "stream" for p in op.get("parameters", []))
