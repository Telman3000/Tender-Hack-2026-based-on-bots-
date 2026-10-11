from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import csv
import io
import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles

from app.config import FRONTEND_DIR
from app.db import db_ready
from app.engine import CatalogEngine
from app.models import AnalyzeRequest, AnalyzeResponse

engine: CatalogEngine | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global engine
    engine = CatalogEngine()
    yield
    if engine:
        engine.close()


app = FastAPI(
    title="Tender Hack 2026 — STE Autofill",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "db_ready": db_ready(),
        "service": "ste-autofill",
    }


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    if not engine:
        raise HTTPException(503, "Engine not ready")
    return engine.analyze(req)


BATCH_MAX = 500
BATCH_WORKERS = max(4, min(8, os.cpu_count() or 4))
_NAME_HEADERS = {"name", "names", "наименование", "наименования", "название", "товар", "text", "query",
                 "описание", "наименование товара", "наименование сте"}


class BatchItem(BaseModel):
    id: str | int | None = None
    text: str | None = ""


class BatchRequest(BaseModel):
    items: list[BatchItem]
    domain_hint: Literal["furniture", "clothing", "tools"] | None = None


def _one(item: dict, hint: str | None) -> dict:
    text = item.get("text") or ""
    base = {"id": item["id"], "text": text}
    if not text.strip():
        return {**base, "error": "Пустое наименование"}
    try:
        r = engine.analyze(AnalyzeRequest(text=text, domain_hint=hint))
        return {**base, **r.model_dump(by_alias=True, mode="json")}
    except Exception as e:  # noqa: BLE001 - one bad row never breaks the batch
        return {**base, "error": f"{type(e).__name__}: {e}"[:300]}


def _summary(results: list[dict], elapsed_ms: float) -> dict:
    code, card, match = Counter(), Counter(), Counter()
    errors = 0
    for r in results:
        if "error" in r and "status" not in r:
            errors += 1
            continue
        code["out_of_scope" if r.get("out_of_scope") else r.get("code_status", "not_found")] += 1
        card[r.get("card_status", "incomplete")] += 1
        match[r.get("status", "not_found")] += 1
    return {
        "total": len(results), "errors": errors,
        "by_code_status": {k: code.get(k, 0) for k in ("determined", "ambiguous", "not_found", "out_of_scope")},
        "by_card_status": {k: card.get(k, 0) for k in ("complete", "incomplete", "invalid")},
        "by_status": {k: match.get(k, 0) for k in ("ok", "need_more", "ambiguous", "error", "not_found")},
        "elapsed_ms": round(elapsed_ms, 1),
    }


def _run(items: list[dict], hint: str | None):
    """Yields results in input order; rows are analysed by a small thread pool on the shared engine."""
    with ThreadPoolExecutor(BATCH_WORKERS) as ex:
        yield from ex.map(lambda it: _one(it, hint), items)


def _wants_stream(request: Request) -> bool:
    q = request.query_params.get("stream", "")
    return q.lower() in ("1", "true", "yes", "ndjson") or "application/x-ndjson" in request.headers.get("accept", "")


def _respond(items: list[dict], hint: str | None, request: Request, extra: dict | None = None):
    if not engine:
        raise HTTPException(503, "Engine not ready")
    if len(items) > BATCH_MAX:
        raise HTTPException(413, f"Слишком много строк: {len(items)}, максимум {BATCH_MAX}")
    t0 = time.perf_counter()
    if _wants_stream(request):
        def gen():
            out = []
            for r in _run(items, hint):
                out.append(r)
                yield json.dumps({"type": "result", **r}, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "summary", **(extra or {}),
                              "summary": _summary(out, (time.perf_counter() - t0) * 1000)}, ensure_ascii=False) + "\n"
        return StreamingResponse(gen(), media_type="application/x-ndjson")
    results = list(_run(items, hint))
    return {"results": results, **(extra or {}), "summary": _summary(results, (time.perf_counter() - t0) * 1000)}


@app.post("/api/analyze/batch")
def analyze_batch(req: BatchRequest, request: Request,
                  stream: str | None = Query(None, description="1 → построчный NDJSON-поток (application/x-ndjson)")):
    if len(req.items) > BATCH_MAX:
        raise HTTPException(413, f"Слишком много строк: {len(req.items)}, максимум {BATCH_MAX}")
    items = [{"id": it.id if it.id is not None else i + 1, "text": it.text or ""} for i, it in enumerate(req.items)]
    return _respond(items, req.domain_hint, request)


def decode_csv(raw: bytes) -> tuple[str, str]:
    """UTF-8 (with or without BOM), UTF-16, else cp1251."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc), ("utf-8" if enc == "utf-8-sig" else enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8 (с заменой символов)"


def parse_names_csv(text: str) -> tuple[list[dict], dict]:
    """One column of names; delimiter «;» or «,» (or tab); optional header; optional id column."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return [], {"delimiter": None, "header": False}
    sample = "\n".join(lines[:50])
    delim = None
    header_cells = [c.strip().lower().lstrip("\ufeff") for c in next(csv.reader([lines[0]]))]
    if any("\t" in ln for ln in lines[:50]):
        delim = "\t"
    elif any(";" in ln for ln in lines[:50]):
        delim = ";"
    elif header_cells and all(c in _NAME_HEADERS or c in ("id", "№", "n", "номер") for c in header_cells) and "," in lines[0]:
        delim = ","  # «name,name» is a header, not a product
    elif any(ln.lstrip().startswith('"') for ln in lines[:50]):
        delim = ","  # quoted CSV: commas inside quotes stay in the name
    if delim is None:
        rows = [[ln] for ln in lines]  # unquoted single column: commas stay in the name
    else:
        rows = [r for r in csv.reader(io.StringIO("\n".join(lines)), delimiter=delim) if any(c.strip() for c in r)]
    col, id_col, header = 0, None, False
    first = [c.strip().lower().lstrip("\ufeff") for c in rows[0]] if rows else []
    if any(c in _NAME_HEADERS for c in first) or (first and first[0] in ("id", "№", "n")):
        header = True
        col = next((i for i, c in enumerate(first) if c in _NAME_HEADERS), len(first) - 1)
        id_col = next((i for i, c in enumerate(first) if c in ("id", "№", "n", "номер")), None)
        rows = rows[1:]
    join_names = header and bool(first) and all(c in _NAME_HEADERS for c in first)
    items = []
    for i, r in enumerate(rows):
        if join_names:
            text = " ".join(c.strip() for c in r if c.strip())
        else:
            text = r[col].strip() if col < len(r) else ""
        if delim is None and header:
            text = " ".join(text.replace(",", " ").split())  # «Стол, письменный» under a name header
        rid = r[id_col].strip() if id_col is not None and id_col < len(r) and r[id_col].strip() else i + 1
        items.append({"id": rid, "text": text})
    _ = sample
    return items, {"delimiter": delim or "none", "header": header}


@app.post("/api/analyze/csv")
async def analyze_csv(request: Request, file: UploadFile = File(...),
                      domain_hint: Literal["furniture", "clothing", "tools"] | None = None,
                      stream: str | None = Query(None, description="1 → построчный NDJSON-поток (application/x-ndjson)")):
    raw = await file.read()
    if len(raw) > 5_000_000:
        raise HTTPException(413, "Файл больше 5 МБ")
    text, enc = decode_csv(raw)
    items, info = parse_names_csv(text)
    if not items:
        raise HTTPException(422, "В файле нет строк с наименованиями")
    if len(items) > BATCH_MAX:
        raise HTTPException(413, f"Слишком много строк: {len(items)}, максимум {BATCH_MAX}")
    return _respond(items, domain_hint, request, {"file": {"name": file.filename, "encoding": enc, **info,
                                                           "rows": len(items)}})


@app.get("/api/demo-cases")
def demo_cases():
    return [
        {
            "title": "Стол офисный (полный)",
            "text": "Стол офисный ДСП высота 750 мм ширина 1200 мм глубина 600 мм цвет серый",
            "domain_hint": "furniture",
        },
        {
            "title": "Стол с опечаткой / неполно",
            "text": "стол офсный дсп высота 1.10 цвет красный",
            "domain_hint": "furniture",
        },
        {
            "title": "Стул",
            "text": "Стул на металлическом каркасе цвет черный материал кожа",
            "domain_hint": "furniture",
        },
        {
            "title": "Рюкзак",
            "text": "Рюкзак школьный цвет синий материал полиэстер объем 28 л",
            "domain_hint": "clothing",
        },
        {
            "title": "Дрель-шуруповерт",
            "text": "Дрель-шуруповерт аккумуляторная мощность 10.8 Вт цвет серый",
            "domain_hint": "tools",
        },
        {
            "title": "Только название",
            "text": "молоток",
            "domain_hint": "tools",
        },
    ]


# Static UI
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        return {"message": "UI missing", "api": "/docs"}
    return FileResponse(index_path)
