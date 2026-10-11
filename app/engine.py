from __future__ import annotations

import re
import sqlite3
import time

from app.catalog import Catalog
from app.config import CHAR_ALIASES
from app.db import connect, db_ready
from app.matcher import OK_MARGIN, candidates_view, narrow_ktru, _cand
from app.models import (AnalyzeRequest, AnalyzeResponse, CharSource, Completeness, Correction, FillCounter, Issue,
                        MissingCharacteristic, NextStep, ParsedCharacteristic, Question)
from app.units import canon_unit, convert, dimension, to_number
from app.validate import is_numeric_spec, numeric_view
from app.catalog import norm
from app.parser import RawKV, detect_domain, domain_scores, guess_product_name, parse_free_text, prepare_text, strip_html
from app.unify import order_characteristics, unify_characteristics

SUPPORTED = {"furniture": "мебель", "clothing": "одежда", "tools": "инструменты"}
OUT_OF_SCOPE_MSG = ("Не наша категория: товар не относится к поддерживаемым категориям "
                    "(мебель, одежда, инструменты) или не распознан. Код КТРУ не подбирается.")


_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))


def _drop_invisible(text: str) -> tuple[str, list[int] | None]:
    """Remove zero-width characters / soft hyphens; return cleaned text and cleaned->original index map."""
    if not any(ord(ch) in _INVISIBLE for ch in text):
        return text, None
    out, back = [], []
    for i, ch in enumerate(text):
        if ord(ch) not in _INVISIBLE:
            out.append(ch)
            back.append(i)
    back.append(len(text))
    return "".join(out), back


_COMPLEMENT = {"для", "из", "с", "со", "в", "во", "на", "от", "по", "под", "без", "к", "при"}


def _name_head(ktru_name: str) -> list[str]:
    """Head of a KTRU name: words before its complement («Сумка для ноутбука» -> [сумка])."""
    out = []
    for w in norm(ktru_name).split():
        if w in _COMPLEMENT:
            break
        out.append(w)
    return out


def _name_overlap(product: str, ktru_name: str) -> bool:
    """The item word must match the head of the KTRU name; words of «для X» complements do not count."""
    st = lambda ws: {w[:4] for w in ws if len(w) >= 3}  # noqa: E731
    return bool(st(norm(product).split()) & st(_name_head(ktru_name)))


def choose_question(group, filled_names: set[str]) -> Question | None:
    """One question only when the choice cannot be made for the user.

    Asked when the remaining codes have several different names, or when an unfilled required enum
    characteristic splits them. The field that splits the group into the most distinct values wins.
    """
    entries = [e for _, e in group]
    if len(entries) < 2:
        return None
    names = list(dict.fromkeys(e.name for e in entries))
    filled = {n.lower() for n in filled_names}
    best = None
    keys = dict.fromkeys(k for e in entries for k, sp in e.specs.items() if sp.enums and k not in filled)
    for k in keys:
        per_code = [frozenset(norm(v) for v in e.specs[k].enums) if k in e.specs else frozenset() for e in entries]
        distinct = len(set(per_code))
        if distinct < 2:
            continue
        req = any(e.specs[k].required for e in entries if k in e.specs)
        if len(names) < 2 and not req:
            continue  # same name, optional field: not worth a question, the UI just highlights it
        score = (distinct, req)
        if best is None or score > best[0]:
            best = (score, k)
    if best is None:
        if len(names) < 2:
            return None
        return Question(field="Наименование", reason="Подходят позиции КТРУ с разными наименованиями",
                        options=names[:6], remaining_by_option={n: sum(e.name == n for e in entries) for n in names[:6]},
                        candidates_now=len(entries))
    k = best[1]
    from collections import Counter
    cnt: Counter = Counter()
    label = {}
    for e in entries:
        sp = e.specs.get(k)
        for v in dict.fromkeys(sp.enums if sp else []):
            cnt[norm(v)] += 1
            label.setdefault(norm(v), v)
    opts = [label[v] for v, _ in cnt.most_common(6)]
    name = next(e.specs[k].name for e in entries if k in e.specs)
    reason = ("Подходят позиции КТРУ с разными наименованиями" if len(names) > 1
              else f"Обязательная характеристика «{name}» различает {len(entries)} подходящих кодов")
    return Question(field=name, reason=reason, options=opts,
                    remaining_by_option={label[v]: c for v, c in cnt.most_common(6)}, candidates_now=len(entries))


def _step_field(t: str) -> str | None:
    if t.startswith("Укажите: "):
        return t.split(": ", 1)[1]
    if t.startswith("Исправьте «"):
        return t[len("Исправьте «"):].split("»", 1)[0]
    return None


def _find(text: str, frag: str | None) -> list[int] | None:
    if not frag:
        return None
    i = text.lower().find(frag.lower())
    return [i, i + len(frag)] if i >= 0 else None


def _add_spans(text: str, chars, issues, user_rows: set[str]) -> None:
    for c in chars:
        if c.value and (c.raw_name or c.name).lower() not in user_rows:
            c.span = _find(text, c.user_input) or _find(text, c.value)
    for i in issues:
        frag = (i.value or "").split(" ")[0] if i.type == "unit" else i.value
        i.span = _find(text, frag)
        if i.span is None and i.field:
            i.span = _find(text, i.field)


def _corrections(orig: str, text: str, issues, conv) -> list[Correction]:
    out: list[Correction] = []
    if text != orig:
        out.append(Correction(field="Наименование", kind="translit", from_=orig, to=text, span=[0, len(orig)]))
    for i in issues:
        if i.type == "typo" and i.value and i.expected and i.value != orig:
            kind = "typo" if i.field in ("Наименование", "Описание") else "autofix"
            out.append(Correction(field=i.field, kind=kind, from_=i.value, to=i.expected, span=_find(orig, i.value)))
        elif i.type == "unit" and i.severity == "warning" and i.value and i.suggestions:
            out.append(Correction(field=i.field, kind="unit", from_=i.value, to=i.suggestions[0],
                                  span=_find(orig, i.value)))
    for kind, field, frm, to in conv:
        out.append(Correction(field=field, kind=kind, from_=frm, to=to, span=_find(orig, frm)))
    return out


_OTHER_PRODUCTS = {
    "стол", "стола", "стул", "стула", "кресло", "кресла", "шкаф", "шкафа",
    "диван", "дивана", "стеллаж", "стеллажа", "тумба", "тумбы", "молоток", "молотка",
    "дрель", "дрели", "куртка", "куртки", "костюм", "футболка", "футболки",
    "ключ", "ключа", "отвертка", "отвёртка", "лобзик", "труба", "трубы",
}
_NEG_SKIP = {"менее", "более", "меньше", "больше"}


def _second_product(text: str, head: str) -> str | None:
    parts = re.split(r"\s+и\s+", text or "", maxsplit=1, flags=re.I)
    if len(parts) < 2:
        return None
    words = norm(parts[1]).split()
    if not words or words[0] not in _OTHER_PRODUCTS:
        return None
    h = (norm(head).split() or [""])[0]
    if h and (words[0].startswith(h[:4]) or h.startswith(words[0][:4])):
        return None
    return words[0]


def _negations(text: str) -> list[str]:
    out = []
    for m in re.finditer(r"\bбез\s+([а-яё\-]{4,})", text or "", re.I):
        out.append(f"без {m.group(1)}")
    for m in re.finditer(r"\bне\s+([а-яё\-]{4,})", text or "", re.I):
        if norm(m.group(1)) in _NEG_SKIP:
            continue
        out.append(f"не {m.group(1)}")
    return out


def _value_conflicts(raw: list) -> list[Issue]:
    """Same label twice with different numbers. A size triple 661х703х1542 is three labels, not a conflict."""
    groups: dict[str, list] = {}
    for item in raw:
        if item.value and not getattr(item, "bound", None):
            groups.setdefault(item.name.strip().lower(), []).append(item)
    issues = []
    for group in groups.values():
        keys = []
        for item in group:
            n = to_number(str(item.value))
            if n is None:
                keys.append(("s", str(item.value).strip().lower()))
                continue
            u = canon_unit(item.unit)
            dim = dimension(u) if u else None
            base = {"mass": "кг", "length": "мм", "power": "Вт", "voltage": "В"}.get(dim or "")
            conv = convert(n, u, base) if base and u else None
            keys.append(("n", round(conv if conv is not None else n, 4)))
        if len(set(keys)) > 1:
            shown = ", ".join(f"{item.value} {item.unit or ''}".strip() for item in group)
            issues.append(Issue.make(
                "mismatch", field=group[0].name, value=shown, severity="error",
                message=f"«{group[0].name}»: в тексте несколько разных значений ({shown})",
            ))
    return issues


class CatalogEngine:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self.conn = conn or connect()
        self.catalog: Catalog | None = None
        if db_ready():
            t = time.perf_counter()
            self.catalog = Catalog(self.conn)
            self.load_ms = round((time.perf_counter() - t) * 1000)

    def close(self) -> None:
        if self._own_conn:
            self.conn.close()

    @staticmethod
    def _merge(raw: list[RawKV], req: AnalyzeRequest) -> tuple[list[RawKV], set[str]]:
        """Rows sent by the UI override parsed ones (by name) and are always echoed back."""
        if not req.characteristics:
            return raw, set()
        given = {c.name.strip().lower(): c for c in req.characteristics if c.name.strip()}
        merged = [r for r in raw if r.name.lower() not in given]
        for c in req.characteristics:
            if c.name.strip():
                merged.append(RawKV(name=c.name.strip(), value=(c.value or "").strip(), unit=c.unit or None))
        return merged, set(given)

    def _next_steps(self, nr, chars, issues) -> list[str]:
        """Unique hints; characteristic names exactly as in the table, never for filled ones."""
        filled = {c.name for c in chars if c.value}
        table = {c.name for c in chars}
        out: list[str] = []
        asked: set[str] = set()
        for st in nr.next_steps:
            if st.startswith("Уточните: "):
                n = st.split(": ", 1)[1]
                sp = self.catalog.find_spec(nr.best, n) if nr.best is not None else None
                n = sp.name if sp is not None else n
                if n in filled or n in asked:
                    continue
                if n not in table:
                    if sp is None:
                        continue
                    lo, hi, nu = numeric_view(sp, None) if is_numeric_spec(sp) else (None, None, canon_unit(sp.unit) or sp.unit)
                    chars.append(ParsedCharacteristic(
                        name=sp.name, raw_name="", canonical_name=sp.name, value="",
                        unit=nu, min=lo, max=hi, source=CharSource.KTRU, required=sp.required,
                        allowed=sp.allowed_enums(), confidence=0.0,
                        notes="Отличительная характеристика группы вариаций КТРУ",
                    ))
                    table.add(sp.name)
                asked.add(n)
                out.append(f"Укажите: {n}")
            elif st not in out:
                out.append(st)
        for i in issues:
            if i.type == "missing" and i.field and i.field not in filled and i.field not in asked:
                asked.add(i.field)
                out.append(f"Укажите: {i.field}")
        return out

    def _canon_key(self, name: str, best) -> str:
        sp = self.catalog.find_spec(best, name) if best is not None else None
        if sp is not None:
            return sp.name.lower()
        return CHAR_ALIASES.get(name.strip().lower(), name.strip()).lower()

    def _dedupe_by_canonical(self, raw: list[RawKV], user_rows: set[str], best) -> list[RawKV]:
        """A frontend row replaces any text-parsed row with the same canonical name."""
        user_items = [r for r in raw if r.name.lower() in user_rows]
        keys = {self._canon_key(r.name, best) for r in user_items}
        text_items = [r for r in raw if r.name.lower() not in user_rows
                      and self._canon_key(r.name, best) not in keys]
        return text_items + user_items

    def analyze(self, req: AnalyzeRequest) -> AnalyzeResponse:
        t0 = time.perf_counter()
        if self.catalog is None:
            return AnalyzeResponse(
                input_text=req.text, detected_domain=None, product_guess=None,
                characteristics=[], narrowing=[], best_ktru=None, status="error",
                issues=[Issue.make("missing", "База catalog.db не собрана", severity="error",
                                   suggestions=["python -m scripts.build_index --materials <папка материалов>"])],
                next_steps=["Собрать индекс из материалов хакатона"],
            )
        src, back = _drop_invisible(strip_html(req.text))  # spans are mapped back to req.text at the end
        fully_latin = bool(src) and not re.search(r"[а-яё]", src, re.I) and bool(re.search(r"[a-z]", src, re.I))
        text = prepare_text(src)
        # Only the product head may override a hint. A later word («стойка» in «воротник-стойка») must not.
        head_name = guess_product_name(text)
        first = (norm(head_name).split() or [""])[0]
        hs = domain_scores(first)
        hb = max(hs, key=hs.get)
        head_domain = hb if hs[hb] > 0 else None
        hint = req.domain_hint if req.domain_hint in SUPPORTED else None
        if hint and (head_domain is None or head_domain == hint):
            domain = hint
        else:
            domain = head_domain or detect_domain(text, None)
        product, raw = parse_free_text(text, domain)
        product = guess_product_name(text) or product
        raw, user_rows = self._merge(raw, req)

        filled = [r for r in raw if r.value]
        nr = narrow_ktru(self.catalog, product, filled, domain, domain_detected=domain is not None, text=text)
        # Hint-only pool and the winner's head noun does not match: that is a random code.
        head = (norm(product).split() or [""])[0]
        head_known = bool(head) and hint and (head in self.catalog.vocab(hint) or self.catalog.known_form(head, hint))
        weak_hint = bool(nr.best is not None and hint and head_domain is None and not nr.anchored and not head_known)
        if weak_hint:
            nr.best, nr.group, nr.shown, nr.next_steps = None, [], [], []
            nr.issues = [i for i in nr.issues if i.type != "ambiguous"]
        if domain is None and nr.best is not None and not nr.anchored and not _name_overlap(product, nr.best.name):
            # no category recognised and the best name shares no word with the item: not our category
            nr.best, nr.group, nr.shown, nr.next_steps, nr.issues = None, [], [], [], []
        matched_head = (norm(nr.query or product).split() or [""])[0]
        head_known = bool(matched_head) and (
            matched_head in self.catalog.vocab(domain) or self.catalog.known_form(matched_head, domain))
        if nr.best is not None and not nr.anchored and nr.margin < OK_MARGIN and not head_known:
            # «Малаток» is not a vise: an unknown head with a tiny gap must not become a code.
            nr.best, nr.group, nr.shown, nr.next_steps = None, [], [], []
            nr.issues = [i for i in nr.issues if i.type != "ambiguous"]
        forced_oos = False
        if nr.best is not None:
            qall, nall = norm(text), norm(nr.best.name)
            tire = any(w in ("шина", "шины", "автошина") or w.startswith("автошин") or w.startswith("покрыш")
                       for w in qall.split())
            tire_hit = any(w.startswith("шин") or w.startswith("покрыш") for w in nall.split())
            if ("вентури" in nall and "вентури" not in qall) or ("коляск" in qall and "коляск" not in nall) or (tire and not tire_hit):
                nr.best, nr.group, nr.shown, nr.next_steps = None, [], [], []
                nr.issues = [i for i in nr.issues if i.type != "ambiguous"]
                forced_oos = True
        second = _second_product(text, product)
        if second:
            nr.issues.append(Issue.make(
                "two_products", severity="warning",
                message=f"В описании два товара, проверена только первая позиция. Второй: «{second}».",
            ))
        for neg in _negations(text):
            nr.issues.append(Issue.make(
                "negation", severity="warning", value=neg,
                message=f"Отрицание «{neg}» не записано в карточку как значение. Уточните характеристику.",
            ))
        if req.characteristics and nr.best is not None:
            raw = self._dedupe_by_canonical(raw, user_rows, nr.best)
            filled = [r for r in raw if r.value]
        issues = list(nr.issues)
        if fully_latin and text != src:
            issues.append(Issue.make(
                "typo", field="Наименование", value=src, expected=text, suggestions=[text],
                severity="warning",
                message=f"Описание набрано латиницей — распознано как «{text}». Проверьте и введите кириллицей",
            ))
        conv: list = []
        alts = [e for _, e in (nr.shown or [])[:10]]
        vdomain = domain or (nr.best.domain if nr.best is not None else None)
        chars, char_issues = unify_characteristics(self.catalog, raw, vdomain, nr.best, user_rows, text, conv, alts)
        issues.extend(char_issues)
        next_steps = self._next_steps(nr, chars, issues)
        for i in issues:
            if i.severity == "error" and i.field:
                next_steps.append(f"Исправьте «{i.field}»" + (f": {i.suggestions[0]}" if i.suggestions else ""))

        issues.extend(_value_conflicts(raw))
        has_sus = any(c.suspicious for c in chars)
        # precedence: not_found > error > need_more > ambiguous > ok
        missing_required = any(c.required and not c.value for c in chars)
        if nr.best is None:
            status = "not_found"
        elif any(i.severity == "error" for i in issues):
            status = "error"
        elif not filled or missing_required:
            status = "need_more"
        elif (any(i.type in ("ambiguous", "typo") for i in issues) or nr.margin < OK_MARGIN):
            status = "ambiguous"
            if not any(i.type == "ambiguous" for i in issues):
                issues.append(Issue.make(
                    "ambiguous", severity="warning",
                    message=f"Отрыв лучшего кода от следующего ({nr.margin:.1f}) мал — проверьте кандидатов",
                    suggestions=["Добавьте отличительные характеристики"],
                ))
        else:
            status = "ok"
        if status == "ok" and (has_sus or any(i.type in ("two_products", "negation") for i in issues)):
            status = "need_more"
        if not filled:
            issues.append(Issue.make(
                "missing", "Не удалось выделить характеристики из текста", severity="warning",
                suggestions=["Формат: «Стол офисный ЛДСП высота 750 мм цвет серый»"],
            ))

        next_steps = list(dict.fromkeys(next_steps))[:10]
        req_fields = {c.name for c in chars if c.required}
        detail = [NextStep(text=t, field=f, required=(f is None or f in req_fields or t.startswith("Исправьте")))
                  for t in next_steps for f in [_step_field(t)]]
        _add_spans(src, chars, issues, user_rows)
        corrections = _corrections(src, text, issues, conv)
        for obj in (*chars, *issues, *corrections):
            if obj.span and back is not None:
                obj.span = [back[obj.span[0]], back[max(obj.span[1] - 1, obj.span[0])] + 1]
        chars = order_characteristics(chars)
        foreign = not re.search(r"[а-яё]", req.text or "", re.I)
        out_of_scope = weak_hint or forced_oos or (
            nr.best is None and ((domain is None and hint is None) or foreign)
        )
        if out_of_scope:
            issues.append(Issue.make("out_of_scope", OUT_OF_SCOPE_MSG, severity="warning",
                                     suggestions=list(SUPPORTED.values())))
        ktru_rows = [c for c in chars if c.source == CharSource.KTRU]
        missing = [MissingCharacteristic(name=c.name, required=c.required, allowed=c.allowed, min=c.min,
                                         max=c.max, unit=c.unit)
                   for c in sorted((c for c in ktru_rows if not c.value), key=lambda c: not c.required)]
        n_total = len(nr.best.specs) if nr.best is not None else 0
        n_filled = sum(1 for c in ktru_rows if c.value)
        rq = [c for c in ktru_rows if c.required]
        fill = None if (nr.best is None or n_total == 0) else FillCounter(
            filled=n_filled, total=max(n_total, len(ktru_rows)),
            required_filled=sum(1 for c in rq if c.value), required_total=len(rq),
            text=(f"Заполнено {n_filled} из {max(n_total, len(ktru_rows))} характеристик КТРУ "
                  f"(обязательных {sum(1 for c in rq if c.value)} из {len(rq)})"))
        no_chars_msg = "У позиции КТРУ нет характеристик" if nr.best is not None and n_total == 0 else None
        question = choose_question(nr.group, {c.name for c in chars if c.value}) if nr.best is not None else None
        has_error = any(i.severity == "error" for i in issues)
        has_new = any(i.type in ("new_property", "negation", "two_products") for i in issues) or has_sus
        req_rows = [c for c in chars if c.required]
        opt_rows = [c for c in chars if not c.required]
        names = {e.name for _, e in nr.group} if nr.group else ({nr.best.name} if nr.best else set())
        group = nr.group if len(nr.group) > 1 else []
        no_specs = nr.best is not None and n_total == 0
        return AnalyzeResponse(
            code_status="not_found" if nr.best is None else ("determined" if len(names) <= 1 else "ambiguous"),
            card_status="invalid" if has_error else (
                "incomplete" if (no_specs or has_new or any(not c.value for c in req_rows) or not filled) else "complete"),
            completeness=Completeness(
                required_total=len(req_rows), required_filled=sum(1 for c in req_rows if c.value),
                optional_total=len(opt_rows), optional_filled=sum(1 for c in opt_rows if c.value)),
            corrections=corrections,
            next_steps_detail=detail,
            input_text=req.text,
            detected_domain=domain,
            product_guess=nr.query or product,
            characteristics=chars,
            issues=issues,
            narrowing=nr.steps,
            best_ktru=_cand(nr.best, nr.group[0][0] if nr.group else 0.0) if nr.best else None,
            candidates=candidates_view(nr.shown[:5] if len(nr.group) > 1 else []),
            status=status,
            next_steps=[d.text for d in detail if d.required],
            missing_characteristics=missing,
            fill=fill,
            question=question,
            out_of_scope=out_of_scope,
            message=OUT_OF_SCOPE_MSG if out_of_scope else no_chars_msg,
            debug={"raw_count": len(raw), "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1)},
        )
