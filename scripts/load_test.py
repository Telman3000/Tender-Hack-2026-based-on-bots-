"""Load test for /api/analyze: N concurrent requests over a mix of realistic queries.

Usage: python scripts/load_test.py --url http://127.0.0.1:8802 [--n 50] [--concurrency 50] [--pid PID]
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

QUERIES = [
    "Стол офисный ЛДСП высота 750 мм ширина 1200 мм цвет серый",
    "Стол письменный 1200х600х750 мм ЛДСП",
    "Шкаф для документов ШхГхВ 800x400x1850",
    "Стул офисный",
    "Футболка мужская хлопок 100% размер 48",
    "Костюм рабочий мужской размер 48-50 рост 170-176",
    "Куртка зимняя мужская размер 50",
    "Ботинки рабочие кожаные размер 42",
    "Молоток слесарный масса 500 г",
    "Ключ гаечный 17х19 мм длина 270 мм",
]


def rss_mb(pid: int | None) -> float | None:
    if not pid:
        return None
    try:
        import psutil  # optional
        p = psutil.Process(pid)
        return round(sum(c.memory_info().rss for c in [p] + p.children(recursive=True)) / 2**20, 1)
    except Exception:
        return None


def one(url: str, text: str) -> tuple[float, int]:
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(url + "/api/analyze", data=body, headers={"Content-Type": "application/json"})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()
        code = r.status
    return (time.perf_counter() - t) * 1000, code


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8802")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--concurrency", type=int, default=50)
    ap.add_argument("--pid", type=int, default=None, help="server PID for RSS (needs psutil)")
    a = ap.parse_args()
    one(a.url, QUERIES[0])  # warm-up
    before = rss_mb(a.pid)
    barrier = threading.Barrier(min(a.n, a.concurrency))

    def task(i: int):
        if i < a.concurrency:
            barrier.wait()
        return one(a.url, QUERIES[i % len(QUERIES)])

    t0 = time.perf_counter()
    with ThreadPoolExecutor(a.concurrency) as ex:
        res = list(ex.map(task, range(a.n)))
    wall = time.perf_counter() - t0
    lat = sorted(r[0] for r in res)
    ok = sum(1 for r in res if r[1] == 200)
    out = {
        "requests": a.n, "concurrency": a.concurrency, "ok": ok,
        "p50_ms": round(statistics.median(lat), 1),
        "p95_ms": round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 1),
        "max_ms": round(lat[-1], 1),
        "throughput_rps": round(a.n / wall, 1), "wall_s": round(wall, 2),
        "rss_before_mb": before, "rss_after_mb": rss_mb(a.pid),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
