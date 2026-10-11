"""Measure analyze() latency for defense slides. Usage: python scripts/measure_latency.py"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DB_PATH  # noqa: E402
from app.engine import CatalogEngine  # noqa: E402
from app.models import AnalyzeRequest  # noqa: E402

QUERIES = [
    "Стол офисный ЛДСП высота 750 мм ширина 1200 мм цвет серый",
    "Молоток слесарный масса 500 г",
    "Футболка мужская хлопок 100% размер 48",
    "Ключ гаечный разводной длина 270 мм",
    "Куртка зимняя мужская размер 50",
]


def main() -> int:
    if not DB_PATH.exists():
        print("catalog.db missing — run scripts/build_index first", file=sys.stderr)
        return 1
    eng = CatalogEngine()
    eng.analyze(AnalyzeRequest(text="стол"))  # warmup
    wall: list[float] = []
    engine_ms: list[float] = []
    for _ in range(30):
        for q in QUERIES:
            t0 = time.perf_counter()
            r = eng.analyze(AnalyzeRequest(text=q))
            wall.append((time.perf_counter() - t0) * 1000)
            engine_ms.append(float(r.debug.get("elapsed_ms", 0)))
    eng.close()
    wall.sort()
    engine_ms.sort()
    n = len(wall)
    p50_w = statistics.median(wall)
    p95_w = wall[int(0.95 * (n - 1))]
    p50_e = statistics.median(engine_ms)
    p95_e = engine_ms[int(0.95 * (n - 1))]
    under = sum(1 for x in engine_ms if x < 100) / n * 100
    print(f"samples={n} queries={len(QUERIES)} repeats=30")
    print(f"wall_ms p50={p50_w:.1f} p95={p95_w:.1f} max={max(wall):.1f}")
    print(f"engine_ms(debug.elapsed_ms) p50={p50_e:.1f} p95={p95_e:.1f} max={max(engine_ms):.1f}")
    print(f"share_engine_under_100ms={under:.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
