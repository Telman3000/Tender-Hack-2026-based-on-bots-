from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
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
