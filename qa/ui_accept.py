"""Приёмка экрана на вводах из docs/demo_script.md.

    python qa/ui_accept.py --base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

TYPO = "Дрэль ударная мощность 0,65 кВт"
QUESTION = "Ключ"
CONFLICT = "Стол письменный высота 750 мм высота 900 мм"
EXTRA = "Кресло офисное обивка ткань цвет черный, экологичность: E1"

WAIT_MS = 20000
SCRIPT = Path(__file__).resolve().parents[1] / "docs" / "demo_script.md"


def script_table() -> dict[str, dict]:
    rows = {}
    if not SCRIPT.exists():
        return rows
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 8 or not cells[1].startswith("`"):
            continue
        text = cells[1].strip("`")
        try:
            rows[text] = {"match_status": cells[3], "card_status": cells[4],
                          "area_size": int(cells[5]), "checked_count": int(cells[6]), "compatible_count": int(cells[7])}
        except ValueError:
            continue
    return rows


class Report:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def check(self, group: str, name: str, ok: bool, detail=None) -> bool:
        self.items.append({"group": group, "check": name, "ok": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'}  {group}: {name}" + (f"  [{detail}]" if detail not in (None, "") and not ok else ""))
        return bool(ok)

    @property
    def failed(self) -> list[dict]:
        return [x for x in self.items if not x["ok"]]


def launch(p):
    for kw in ({}, {"channel": "chrome"}, {"channel": "msedge"}):
        try:
            return p.chromium.launch(**kw)
        except Exception:
            continue
    raise RuntimeError("Не найден Chromium: pip install playwright && python -m playwright install chromium")


def settled(pg, text: str | None = None) -> None:
    pg.wait_for_function(
        """(t) => {
            const st = document.getElementById('status');
            if (!st || st.className.includes('busy')) return false;
            if (t === null) return true;
            const hl = document.getElementById('hl');
            return !!hl && !document.getElementById('source').hidden && hl.textContent.trim() === t;
        }""",
        arg=text,
        timeout=WAIT_MS,
    )
    pg.wait_for_timeout(150)


def submit(pg, text: str, domain: str = "") -> None:
    pg.fill("#text", text)
    pg.select_option("#domain", domain)
    pg.click("#run")
    settled(pg, text.strip())


def badge(pg, sel: str) -> str | None:
    loc = pg.locator(sel)
    return loc.get_attribute("data-status") if loc.count() else None


def counter(pg, sel: str) -> int | None:
    loc = pg.locator(sel)
    if not loc.count():
        return None
    raw = loc.inner_text().strip()
    return int(raw) if raw.isdigit() else None


def screen_numbers(pg) -> dict:
    return {
        "area_size": counter(pg, "#areaSize"),
        "checked_count": counter(pg, "#checkedCount"),
        "compatible_count": counter(pg, "#compatibleCount"),
    }


def as_in_script(rep: Report, pg, group: str, text: str, table: dict) -> None:
    want = table.get(text)
    if want is None:
        rep.check(group, f"шаг «{text}» есть в таблице docs/demo_script.md", False)
        return
    got = {"match_status": badge(pg, "#matchBadge"), "card_status": badge(pg, "#cardBadge"), **screen_numbers(pg)}
    rep.check(group, "статусы и числа на экране совпадают с docs/demo_script.md", got == want, f"экран {got}, сценарий {want}")


def common(rep: Report, pg, group: str, api: dict) -> None:
    rep.check(group, "статус подбора на экране совпадает с API", badge(pg, "#matchBadge") == api.get("match_status"),
              f"экран {badge(pg, '#matchBadge')}, API {api.get('match_status')}")
    rep.check(group, "статус карточки на экране совпадает с API", badge(pg, "#cardBadge") == api.get("card_status"),
              f"экран {badge(pg, '#cardBadge')}, API {api.get('card_status')}")
    search = api.get("search") or {}
    nums = screen_numbers(pg)
    want = {k: search.get(k) for k in nums}
    rep.check(group, "area_size, checked_count, compatible_count на экране равны ответу API", nums == want, f"экран {nums}, API {want}")


def run(base: str, out: Path) -> Report:
    rep = Report()
    out.mkdir(parents=True, exist_ok=True)
    responses: dict[str, dict] = {}
    errors: list[str] = []
    table = script_table()
    rep.check("сценарий", "в docs/demo_script.md есть таблица шести шагов", len(table) == 6, sorted(table))
    with sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})
        pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
        pg.on("pageerror", lambda e: errors.append(str(e)))

        def on_response(r):
            if "/api/analyze" in r.url and r.request.method == "POST":
                try:
                    body = json.loads(r.request.post_data or "{}")
                    responses[body.get("text", "")] = r.json()
                except Exception:
                    pass

        pg.on("response", on_response)
        shot = lambda name: pg.screenshot(path=str(out / f"{name}.png"), full_page=True)
        pg.goto(base + "/", wait_until="networkidle")

        g = "1. опечатка с единицей"
        submit(pg, TYPO, "tools")
        api = responses.get(TYPO, {})
        shot("1_typo")
        common(rep, pg, g, api)
        as_in_script(rep, pg, g, TYPO, table)
        corr = pg.locator("#corrBlock").inner_text() if pg.locator("#corrBlock").count() else ""
        rep.check(g, "показано исправление опечатки «Дрэль» → «дрель»", "Дрэль" in corr and "дрель" in corr, corr[:120])
        power = next((c for c in api.get("characteristics", []) if c.get("name") == "Мощность"), None)
        rep.check(g, "мощность приведена к 650 Вт", bool(power) and power.get("value") == "650" and power.get("unit") == "Вт", power)
        row = pg.locator('#chars tr[data-name="мощность"]')
        rep.check(g, "строка «Мощность» есть в таблице КТРУ", row.count() == 1)
        if row.count() and power:
            row.locator(".char-name").click()
            pg.wait_for_timeout(200)
            span = power.get("span") or {}
            start, end = (span.get("start"), span.get("end")) if isinstance(span, dict) else (span[0], span[1])
            marked = pg.locator("#hl mark.focus").inner_text() if pg.locator("#hl mark.focus").count() else ""
            rep.check(g, "клик по характеристике подсвечивает её span в исходном тексте", marked == TYPO[start:end], f"{marked!r} vs {TYPO[start:end]!r}")
            line = pg.locator("#focusLine").inner_text() if pg.locator("#focusLine").is_visible() else ""
            rep.check(g, "строка «было / стало»: user_input и значение с единицей",
                      (power.get("user_input") or "") in line and "650 Вт" in line and "БЫЛО" in line.upper() and "СТАЛО" in line.upper(), line)
            shot("1_focus")
        fix = pg.locator("#corrBlock [data-fix]")
        rep.check(g, "есть кнопка «Исправить в тексте»", fix.count() >= 1)
        if fix.count():
            fix.first.click()
            fixed = "Дрель ударная мощность 0,65 кВт"
            settled(pg, fixed)
            rep.check(g, "исправление записано в текст", pg.input_value("#text") == fixed, pg.input_value("#text"))
            rep.check(g, "после исправления опечатка не показывается", not pg.locator("#corrBlock").count()
                      or "Дрэль" not in pg.locator("#corrBlock").inner_text())
            pg.click("#undo")
            settled(pg, TYPO)
            rep.check(g, "«Отменить правку» вернула прошлый текст", pg.input_value("#text") == TYPO, pg.input_value("#text"))
            rep.check(g, "после отмены ответ пересчитан для прошлого текста", pg.locator("#hl").inner_text().strip() == TYPO)

        g = "2. уточняющий вопрос"
        submit(pg, QUESTION, "tools")
        api = responses.get(QUESTION, {})
        shot("2_question")
        common(rep, pg, g, api)
        as_in_script(rep, pg, g, QUESTION, table)
        q = api.get("question") or {}
        rep.check(g, "задан один вопрос с вариантами", pg.locator("#question").count() == 1 and bool(q.get("options")), q)
        before = counter(pg, "#compatibleCount")
        if q.get("options"):
            option = q["options"][-1]
            pg.locator("#question [data-answer]").nth(len(q["options"]) - 1).click()
            answered = f"{QUESTION}, {q['field']}: {option}"
            settled(pg, answered)
            api2 = responses.get(answered, {})
            shot("2_answered")
            after = counter(pg, "#compatibleCount")
            rep.check(g, "ответ дописан в текст", pg.input_value("#text") == answered, pg.input_value("#text"))
            rep.check(g, "compatible_count уменьшился", before is not None and after is not None and after < before, f"{before} → {after}")
            rep.check(g, "на экране показано прежнее значение счётчика", f"было {before}" in pg.locator("#counters").inner_text())
            common(rep, pg, g + " (после ответа)", api2)
            as_in_script(rep, pg, g + " (после ответа)", answered, table)
            extras_shown = pg.locator("#extras tr[data-row]").count()
            rep.check(g + " (после ответа)", "статус «есть непроверенные дополнения» только вместе с блоком дополнений",
                      (badge(pg, "#cardBadge") == "HAS_UNVERIFIED_EXTRAS") == (extras_shown > 0),
                      f"карточка {badge(pg, '#cardBadge')}, строк в дополнениях {extras_shown}")
            pg.click("#undo")
            settled(pg, QUESTION)
            rep.check(g, "«Отменить правку» вернула текст и счётчик", pg.input_value("#text") == QUESTION and counter(pg, "#compatibleCount") == before,
                      f"{pg.input_value('#text')!r}, {counter(pg, '#compatibleCount')}")

        g = "3. конфликт двух значений"
        submit(pg, CONFLICT)
        api = responses.get(CONFLICT, {})
        shot("3_conflict")
        common(rep, pg, g, api)
        as_in_script(rep, pg, g, CONFLICT, table)
        rep.check(g, "статус подбора INPUT_CONFLICT", badge(pg, "#matchBadge") == "INPUT_CONFLICT")
        rep.check(g, "выбор кода остановлен: нет кода и нет вопроса", pg.locator("#best").count() == 0 and pg.locator("#question").count() == 0)
        keep = pg.locator("#conflict [data-keep]")
        rep.check(g, "предложено оставить одно из значений", keep.count() == 2, keep.count())
        if keep.count() == 2:
            keep.first.click()
            resolved = "Стол письменный высота 750 мм"
            settled(pg, resolved)
            rep.check(g, "после выбора конфликт снят", badge(pg, "#matchBadge") != "INPUT_CONFLICT" and pg.input_value("#text") == resolved,
                      f"{badge(pg, '#matchBadge')}, {pg.input_value('#text')!r}")
            as_in_script(rep, pg, g + " (после выбора)", resolved, table)
            pg.click("#undo")
            settled(pg, CONFLICT)
            rep.check(g, "«Отменить правку» вернула конфликт", badge(pg, "#matchBadge") == "INPUT_CONFLICT")

        g = "4. дополнительное свойство"
        submit(pg, EXTRA)
        api = responses.get(EXTRA, {})
        shot("4_extra")
        common(rep, pg, g, api)
        as_in_script(rep, pg, g, EXTRA, table)
        extras = [c for c in api.get("characteristics", []) if c.get("origin") == "new"]
        rep.check(g, "API вернул свойство с origin = new", bool(extras), [c.get("name") for c in extras])
        for c in extras:
            name = c["name"].strip().lower().replace("ё", "е")
            in_extras = pg.locator(f'#extras tr[data-name="{name}"]')
            rep.check(g, f"«{c['name']}» стоит в блоке дополнений с пометкой «дополнение»",
                      in_extras.count() == 1 and "дополнение" in in_extras.inner_text())
            rep.check(g, f"«{c['name']}» нет среди строк КТРУ", pg.locator(f'#chars tr[data-name="{name}"]').count() == 0)

        g = "5. устаревший ответ"
        pg.goto(base + "/", wait_until="networkidle")
        slow_text = "Стол письменный ЛДСП"
        new_text = "Стол письменный ЛДСП высота 750 мм"

        pg.evaluate(
            """() => {
                const plain = window.fetch.bind(window);
                window.__slow = { text: null, ms: 0 };
                window.fetch = async (url, opts) => {
                    const res = await plain(url, opts);
                    let text = null;
                    try { text = JSON.parse(opts && opts.body || "{}").text; } catch (_) {}
                    if (text === window.__slow.text) await new Promise((ok) => setTimeout(ok, window.__slow.ms));
                    return res;
                };
            }"""
        )
        pg.evaluate("(a) => { window.__slow = { text: a[0], ms: a[1] }; }", [slow_text, 300])
        pg.fill("#text", slow_text)
        pg.click("#run")
        pg.wait_for_timeout(50)
        pg.type("#text", " высота 750 мм", delay=5)
        pg.wait_for_timeout(450)
        drawn = pg.locator("#hl").inner_text().strip() if not pg.locator("#source").is_hidden() else ""
        rep.check(g, "ответ на старый текст, пришедший пока пользователь правит текст, не нарисован", drawn != slow_text, drawn)
        settled(pg, new_text)
        rep.check(g, "после паузы нарисован ответ на текущий текст", pg.locator("#hl").inner_text().strip() == new_text)
        pg.evaluate("(a) => { window.__slow = { text: a[0], ms: a[1] }; }", [slow_text, 1200])
        pg.fill("#text", slow_text)
        pg.click("#run")
        pg.wait_for_timeout(100)
        pg.fill("#text", new_text)
        pg.click("#run")
        settled(pg, new_text)
        pg.wait_for_timeout(1500)
        rep.check(g, "поздний ответ на старый запрос не перерисовал экран", pg.locator("#hl").inner_text().strip() == new_text,
                  pg.locator("#hl").inner_text())
        pg.evaluate("() => { window.__slow = { text: null, ms: 0 }; }")

        g = "6. техническая ошибка"
        seen = len(errors)
        pg.route("**/api/analyze", lambda route: route.fulfill(status=500, content_type="application/json", body='{"detail":"Internal Server Error"}'))
        pg.fill("#text", "Стол письменный")
        pg.click("#run")
        settled(pg)
        rep.check(g, "сбой сервера показан как техническая ошибка, не NO_MATCH_IN_SNAPSHOT",
                  badge(pg, "#matchBadge") == "TECHNICAL_ERROR" and pg.locator("#techError").count() == 1, badge(pg, "#matchBadge"))
        pg.unroute("**/api/analyze")
        down = {
            "input_text": "Стол письменный", "detected_domain": None, "product_guess": None, "characteristics": [],
            "issues": [{"type": "missing", "message": "База catalog.db не собрана", "severity": "error"}],
            "narrowing": [], "best_ktru": None, "match_status": "NO_MATCH_IN_SNAPSHOT", "card_status": "INCOMPLETE",
            "search": {"area_size": 0, "checked_count": 0, "compatible_count": 0}, "status": "error",
        }
        pg.route("**/api/analyze", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(down)))
        pg.route("**/api/health", lambda route: route.fulfill(status=200, content_type="application/json", body='{"ok":true,"db_ready":false}'))
        pg.fill("#text", "Стол письменный ")
        pg.click("#run")
        settled(pg)
        rep.check(g, "отказ базы показан как техническая ошибка, не «нет совпадения»",
                  badge(pg, "#matchBadge") == "TECHNICAL_ERROR", badge(pg, "#matchBadge"))
        shot("6_tech_error")
        pg.unroute("**/api/analyze")
        pg.unroute("**/api/health")
        errors[seen:] = [e for e in errors[seen:] if "Failed to load resource" not in e]
        browser.close()
    rep.check("общее", "нет ошибок JavaScript в консоли", not errors, errors[:3])
    (out / "ui_accept.json").write_text(json.dumps(rep.items, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "ste_ui_accept"))
    a = ap.parse_args()
    rep = run(a.base.rstrip("/"), Path(a.out))
    total, bad = len(rep.items), len(rep.failed)
    print(f"\n{total - bad}/{total} проверок прошли. Снимки и отчёт: {a.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
