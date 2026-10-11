"""Sweep analyze/CSV for anomalies; append one-line FLAGS to qa/redteam_sweep.log."""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "http://127.0.0.1:8000"
LOG = Path(__file__).resolve().parent / "redteam_sweep.log"


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()}\t{msg}\n"
    LOG.open("a", encoding="utf-8").write(line)
    print(msg, flush=True)


def analyze(body: dict) -> dict:
    req = urllib.request.Request(
        BASE + "/api/analyze",
        json.dumps(body, ensure_ascii=False).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main() -> None:
    log("SWEEP_START")
    probes = [
        ("en_desk", {"text": "Office desk laminate 1200mm", "domain_hint": "furniture"}),
        ("zh_desk", {"text": "办公桌 1200毫米", "domain_hint": "furniture"}),
        ("tr_desk", {"text": "Yazı masası LMDF 1200 mm", "domain_hint": "furniture"}),
        ("mixed_hint_none", {"text": "Дрель аккумуляторная 18V"}),
        ("zero_width_join", {"text": "Стол письменный\u2060 ЛДСП", "domain_hint": "furniture"}),
        ("soft_hyphen", {"text": "Стол пись\u00adменный", "domain_hint": "furniture"}),
        ("nb_space", {"text": "Стол\u00a0письменный", "domain_hint": "furniture"}),
        ("combining", {"text": "Стол письменны\u0439\u0301", "domain_hint": "furniture"}),
        ("lookalike_k", {"text": "Костюм рабочий K\u0430\u043f\u0440\u043e\u043d", "domain_hint": "clothing"}),
        ("hammer_v", {"text": "Молоток слесарный 18 V", "domain_hint": "tools"}),
        ("suit_shoes", {"text": "Ботинки рабочие костюм комплект", "domain_hint": "clothing"}),
        ("chair_table", {"text": "Стул офисный и стол письменный комплект", "domain_hint": "furniture"}),
    ]
    for label, body in probes:
        try:
            d = analyze(body)
        except Exception as e:
            log(f"FLAG\t{label}\texception\t{e}")
            continue
        bk = d.get("best_ktru") or {}
        code = bk.get("code", "")
        if d.get("status") in ("ok", "need_more") and d.get("card_status") == "complete":
            if any(i.get("type") == "new_property" for i in d.get("issues", [])):
                log(f"FLAG\t{label}\tcomplete_plus_new\t{code}")
        if d.get("status") == "not_found" and not d.get("out_of_scope") and len(body.get("text", "")) > 12:
            if label.startswith(("en_", "zh_", "tr_")):
                log(f"FLAG\t{label}\tlatin_cjk_not_found\t{body['text'][:40]}")
        if code.startswith("28.24") and "молот" in body["text"].lower():
            log(f"FLAG\t{label}\thammer_electric\t{code}")
        if code.startswith("14.12.30.160") and "костюм" in body["text"].lower():
            log(f"FLAG\t{label}\tsuit_to_glasses\t{code}")
    log("SWEEP_END")


if __name__ == "__main__":
    main()
