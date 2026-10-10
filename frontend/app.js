"use strict";
const $ = (id) => document.getElementById(id);
const DEBOUNCE_MS = 600;
const SOURCE_LABELS = { ktru: "КТРУ", portal: "Портал", new: "Новая" };
const STATUS_LABELS = {
  ok: "Код КТРУ определён",
  need_more: "Нужны уточнения",
  ambiguous: "Несколько подходящих кодов",
  not_found: "Товар не распознан",
  error: "Есть ошибки в характеристиках",
};
const STEP_LABELS = { initial: "Все коды", domain: "Категория", okpd2: "ОКПД2", name: "Наименование" };

const state = { chars: [], data: null, seq: 0, timer: null, dirty: new Map(), textNote: false, origText: null, baseText: null, lastKey: null };
const statusLabel = (st) => STATUS_LABELS[st] || (st ? "Статус: " + st : "");

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}
const norm = (s) => String(s ?? "").trim().toLowerCase();

/* ---------- normalization (new contract + old MVP fields) ---------- */
function normSource(src) {
  const s = norm(src);
  if (s === "ktru" || s === "portal" || s === "new") return s;
  return "new"; // старое значение "user" и неизвестные — новая характеристика
}
function normChar(c) {
  const allowed = c.allowed_values || c.allowed || c.options || null;
  return {
    name: c.name ?? c.canonical_name ?? "",
    user_input: c.user_input ?? c.raw_name ?? "",
    value: c.value ?? "",
    unit: c.unit ?? "",
    source: normSource(c.source),
    required: !!c.required,
    allowed: Array.isArray(allowed) && allowed.length ? allowed.map(String) : null,
    min: c.min ?? (c.range ? c.range.min : undefined) ?? undefined,
    max: c.max ?? (c.range ? c.range.max : undefined) ?? undefined,
    suspicious: !!c.suspicious,
  };
}
function normIssue(i) {
  let suggestions = Array.isArray(i.suggestions) ? i.suggestions : [];
  if (!suggestions.length && i.suggestion) suggestions = [i.suggestion];
  return {
    type: i.type || i.kind || "warning",
    field: i.field ?? null,
    value: i.value ?? "",
    expected: i.expected ?? "",
    suggestions: suggestions.slice(0, 3).map(String),
    message: i.message || "",
    severity: i.severity || ((i.type || i.kind) === "missing" ? "warning" : "error"),
  };
}
function normSteps(data) {
  return (data.narrowing || []).map((s, idx) => {
    let label = s.label;
    const step = String(s.stage || (typeof s.step === "string" ? s.step : "") || "");
    if (!label) {
      if (step.startsWith("char:")) label = "Характеристика: " + step.slice(5);
      else label = STEP_LABELS[step] || step || (idx === 0 ? "Все коды" : `Шаг ${idx}`);
    }
    return {
      label,
      remaining: Number(s.remaining) || 0,
      removed: s.removed ?? null,
      reason: s.reason || s.note || "",
      removed_codes: s.removed_codes || [],
      top: s.top || [],
    };
  });
}
function getCandidates(data, steps) {
  if (Array.isArray(data.candidates) && data.candidates.length) return data.candidates;
  const last = steps[steps.length - 1];
  return last && last.top ? last.top : [];
}

/* ---------- API ---------- */
function schedule(withChars) {
  clearTimeout(state.timer);
  state.timer = setTimeout(() => analyze(withChars), DEBOUNCE_MS);
}
async function analyze(withChars, fromButton) {
  const text = $("text").value.trim();
  if (!text) { showEmpty(); return; }
  if (!withChars) checkNewText(fromButton);
  const seq = ++state.seq;
  $("status").className = "status idle";
  $("status").textContent = "Проверяем…";
  const body = { text, domain_hint: $("domain").value || null };
  // withChars: правка таблицы -> вся текущая таблица; правка текста -> только «грязные» строки
  // (правки таблицы имеют приоритет над текстом, пока их не сбросили)
  const toPayload = (c) => ({ name: c.name.trim(), value: String(c.value ?? ""), unit: c.unit || null });
  if (withChars) {
    body.characteristics = state.chars.filter((c) => c.name.trim()).map(toPayload);
  } else if (state.dirty.size) {
    body.characteristics = [...state.dirty.values()].filter((c) => c.name.trim()).map(toPayload);
  }
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (seq !== state.seq) return; // устаревший ответ
    if (res.status === 422) { showEmpty("Запрос не принят: " + (typeof data.detail === "string" ? data.detail : "проверьте текст и категорию")); return; }
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Ошибка API");
    state.sentText = text;
    render(data);
  } catch (e) {
    if (seq !== state.seq) return;
    $("status").className = "status error";
    $("status").textContent = "Ошибка";
    $("result").className = "result";
    $("result").innerHTML = `<div class="issue error">${escapeHtml(e.message)}</div>`;
  }
}


const EMPTY_HINT = "Введите описание товара, например: «Кресло офисное обивка ткань цвет черный высота 1080 мм»";
function showEmpty(extra) {
  clearTimeout(state.timer); state.seq++;
  state.data = null; state.chars = []; resetOverrides(); state.lastKey = null;
  $("status").className = "status idle"; $("status").textContent = extra || "Введите описание товара";
  $("result").className = "result empty"; $("result").textContent = EMPTY_HINT;
  drawHighlight();
}

/* ---------- статусы кода и карточки (новый контракт + fallback) ---------- */
const CODE_LABELS = { determined: "определён", ambiguous: "несколько вариантов", not_found: "не найден" };
const KIND_LABELS = { unit: "единицы", autofix: "автоисправление", typo: "опечатка", translit: "транслит" };
function codeStatus(data) {
  let cs = data.code_status;
  if (cs === "found") cs = "determined";
  if (CODE_LABELS[cs]) return cs;
  if (data.status === "not_found" || !data.best_ktru) return "not_found";
  if (data.status === "ambiguous") return "ambiguous";
  return "determined";
}
function completenessOf(data) {
  const c = data.completeness;
  if (c && c.required_total != null) return c;
  const filled = (x) => String(x.value ?? "").trim() !== "";
  const req = state.chars.filter((x) => x.required), opt = state.chars.filter((x) => !x.required);
  return { required_total: req.length, required_filled: req.filter(filled).length, optional_total: opt.length, optional_filled: opt.filter(filled).length };
}
function cardStatus(data, issues, comp) {
  if (["complete", "incomplete", "invalid"].includes(data.card_status)) return data.card_status;
  if (data.status === "error" || issues.some((x) => x.severity === "error" && x.type !== "missing")) return "invalid";
  if (data.status === "not_found" || comp.required_filled < comp.required_total || issues.some((x) => x.type === "missing")) return "incomplete";
  return "complete";
}
function statusBadges(data, issues) {
  const cs = codeStatus(data);
  const comp = completenessOf(data);
  const card = cardStatus(data, issues, comp);
  const nMiss = Math.max(0, (comp.required_total || 0) - (comp.required_filled || 0));
  const cardText = card === "complete" ? "заполнена" : card === "invalid" ? "есть ошибки" : nMiss ? `не хватает обязательных: ${nMiss}` : "неполная";
  const cls = (v) => (v === "determined" || v === "complete" ? "good" : v === "not_found" || v === "invalid" ? "bad" : "mid");
  return `<div class="sbadges"><span class="sbadge ${cls(cs)}" id="codeBadge">Код: ${CODE_LABELS[cs]}</span>
    <span class="sbadge ${cls(card)}" id="cardBadge">Карточка: ${cardText}</span></div>
    ${complLine(data, comp)}`;
}
// «0 из 0» не показываем никогда: у позиции КТРУ может не быть характеристик
const NO_CHARS_TEXT = "У позиции КТРУ нет характеристик";
const compTotal = (comp) => (comp.required_total || 0) + (comp.optional_total || 0);
function noCharsText(data) {
  const m = !isOutOfScope(data) && typeof data.message === "string" && data.message.trim() ? data.message.trim() : "";
  return m || NO_CHARS_TEXT;
}
function complLine(data, comp) {
  if (compTotal(comp) === 0) {
    if (isOutOfScope(data) || !data.best_ktru) return "";
    return `<div class="muted small" id="complLine">${escapeHtml(noCharsText(data))}</div>`;
  }
  const part = (f, t, w) => (t ? `${f}/${t} ${w}` : `${w} нет`);
  return `<div class="muted small" id="complLine">${part(comp.required_filled, comp.required_total, "обязательных")}, ${part(comp.optional_filled, comp.optional_total, "необязательных")}</div>`;
}
function nextStepsBlock(data) {
  let items = Array.isArray(data.next_steps_detail) && data.next_steps_detail.length
    ? data.next_steps_detail.map((x) => (typeof x === "string" ? { text: x, required: true } : { text: x.text || "", required: x.required !== false }))
    : (data.next_steps || []).map((x) => ({ text: String(x), required: true }));
  if (!items.length) return "";
  items = [...items.filter((x) => x.required), ...items.filter((x) => !x.required)];
  return `<div class="block"><h2>Что сделать дальше</h2><ul class="next">${items
    .map((x) => `<li class="${x.required ? "req" : "opt"}">${escapeHtml(x.text)}${x.required ? "" : ' <span class="muted">(необязательно)</span>'}</li>`).join("")}</ul></div>`;
}

/* ---------- было → стало ---------- */
function correctionsList(data) {
  if (Array.isArray(data.corrections)) return data.corrections.map((c) => ({ field: c.field || "", kind: c.kind || "", from: String(c.from ?? ""), to: String(c.to ?? "") })).filter((c) => c.from !== c.to);
  // fallback: user_input против value+unit
  const out = [];
  for (const c of state.chars) {
    const v = String(c.value ?? "").trim();
    if (!c.user_input || !v) continue;
    const to = (v + (c.unit ? " " + c.unit : "")).trim();
    const ui = norm(c.user_input);
    if (ui.includes(norm(to)) || (ui.includes(norm(v)) && (!c.unit || ui.includes(norm(c.unit))))) continue;
    out.push({ field: c.name, kind: /^\d/.test(v) ? "unit" : "autofix", from: c.user_input, to });
  }
  return out;
}
function correctionsBlock(data) {
  const list = correctionsList(data);
  if (!list.length) return "";
  return `<div class="block" id="corrBlock"><h2>Было → стало</h2>${list.map((c) => `<div class="corr">
    <span class="kind">${escapeHtml(KIND_LABELS[c.kind] || c.kind || "исправление")}</span>
    ${c.field ? `<b>${escapeHtml(c.field)}:</b> ` : ""}<span class="from">${escapeHtml(c.from)}</span> → <span class="to">${escapeHtml(c.to)}</span></div>`).join("")}</div>`;
}

/* ---------- подсветка фрагментов в тексте ---------- */
// Фрагменты берутся по span из текста запроса (data.input_text), затем ищутся в ТЕКУЩЕМ тексте
// буквально (ближайшее к исходной позиции вхождение) — так подсветка не съезжает при наборе.
function collectMarks(data) {
  const src = String(data.input_text ?? state.sentText ?? "");
  const marks = [];
  for (const raw of data.issues || []) {
    const i = normIssue(raw);
    if (i.type === "missing") continue;
    let frag = "", pos = -1;
    if (Array.isArray(raw.span) && raw.span.length === 2 && raw.span[1] > raw.span[0]) { frag = src.slice(raw.span[0], raw.span[1]); pos = raw.span[0]; }
    if (!frag && i.value && src.toLowerCase().includes(String(i.value).toLowerCase())) frag = String(i.value);
    if (!frag && i.field) {
      const c = (data.characteristics || []).find((x) => norm(x.name) === norm(i.field));
      if (c && Array.isArray(c.span) && c.span[1] > c.span[0]) { frag = src.slice(c.span[0], c.span[1]); pos = c.span[0]; }
      else if (c && c.user_input) frag = c.user_input;
    }
    if (!frag.trim()) continue;
    marks.push({ frag, pos, sev: i.severity === "error" ? "error" : "warning", msg: i.message || i.type });
  }
  return marks;
}
function drawHighlight() {
  const box = $("hl");
  if (!box) return;
  const text = $("text").value;
  const marks = state.data ? collectMarks(state.data) : [];
  const ranges = [];
  const low = text.toLowerCase();
  for (const m of marks) {
    const f = m.frag.toLowerCase();
    let best = -1, at = low.indexOf(f);
    while (at >= 0) { if (best < 0 || Math.abs(at - m.pos) < Math.abs(best - m.pos)) best = at; at = low.indexOf(f, at + 1); }
    if (best < 0) continue;
    const r = { s: best, e: best + f.length, sev: m.sev, msg: m.msg };
    const ov = ranges.find((x) => r.s < x.e && x.s < r.e);
    if (ov) { if (r.sev === "error") ov.sev = "error"; ov.msg += "; " + r.msg; ov.s = Math.min(ov.s, r.s); ov.e = Math.max(ov.e, r.e); }
    else ranges.push(r);
  }
  if (!ranges.length) { box.hidden = true; box.innerHTML = ""; return; }
  ranges.sort((a, b) => a.s - b.s);
  let html = "", p = 0;
  for (const r of ranges) {
    if (r.s < p) continue;
    html += escapeHtml(text.slice(p, r.s)) + `<mark class="${r.sev}" title="${escapeHtml(r.msg)}">${escapeHtml(text.slice(r.s, r.e))}</mark>`;
    p = r.e;
  }
  html += escapeHtml(text.slice(p));
  box.hidden = false;
  box.innerHTML = html;
}

/* ---------- порядок: КТРУ -> Портал -> Новая (стабильно внутри группы) ---------- */
const SOURCE_RANK = { ktru: 0, portal: 1, new: 2 };
function sortBySource(list) {
  // подозрительные (не подходят к типу товара) — всегда в конце
  return list.map((c, i) => [c, i]).sort((a, b) => ((a[0].suspicious ? 1 : 0) - (b[0].suspicious ? 1 : 0)) || (SOURCE_RANK[a[0].source] - SOURCE_RANK[b[0].source]) || (a[1] - b[1])).map((x) => x[0]);
}

/* ---------- «Допишите ещё n характеристик» ---------- */
const isFilled = (c) => String(c.value ?? "").trim() !== "";
function fillBlock(data, issues) {
  const comp = completenessOf(data);
  const total = (comp.required_total || 0) + (comp.optional_total || 0);
  const filled = (comp.required_filled || 0) + (comp.optional_filled || 0);
  let empty = state.chars.map((c, i) => ({ c, i })).filter((x) => x.c.name.trim() && !isFilled(x.c) && !x.c.suspicious);
  // новое ядро: явный список незаполненных (с allowed/min/max/unit) — источник истины для блока
  if (Array.isArray(data.missing_characteristics)) {
    empty = data.missing_characteristics.filter((m) => m && m.name).map((m) => {
      const i = state.chars.findIndex((c) => norm(c.name) === norm(m.name));
      if (i >= 0 && isFilled(state.chars[i])) return null; // уже заполнено правкой в таблице
      const base = i >= 0 ? state.chars[i] : {};
      return { c: normChar({ source: "ktru", ...base, ...m, required: m.required ?? base.required, value: "" }), i };
    }).filter(Boolean);
  }
  // обязательные из issues(missing), которых нет в таблице
  const extra = issues.filter((x) => x.type === "missing" && x.field && !state.chars.some((c) => norm(c.name) === norm(x.field)))
    .map((x) => ({ c: normChar({ name: x.field, value: "", source: "ktru", required: true }), i: -1 }))
    .filter((x) => !empty.some((e) => norm(e.c.name) === norm(x.c.name)));
  const items = [...empty, ...extra];
  const ordered = [...items.filter((x) => x.c.required), ...items.filter((x) => !x.c.required)];
  if (!ordered.length || !data.best_ktru) return "";
  const nReq = ordered.filter((x) => x.c.required).length;
  const pct = total ? Math.round((filled / total) * 100) : 0;
  const row = ({ c, i }) => {
    let ctl = "";
    if (c.allowed) {
      ctl = `<div class="chips">${c.allowed.slice(0, 15).map((v) => `<button type="button" class="chip" data-fill="${i}" data-fname="${escapeHtml(c.name)}" data-fval="${escapeHtml(v)}">${escapeHtml(v)}</button>`).join("")}${c.allowed.length > 15 ? `<span class="muted">ещё ${c.allowed.length - 15} — в таблице</span>` : ""}</div>`;
    } else if (c.min !== undefined || c.max !== undefined) {
      ctl = `<div class="fill-range"><input type="number" data-frange="${i}" data-fname="${escapeHtml(c.name)}" ${c.min != null ? `min="${c.min}"` : ""} ${c.max != null ? `max="${c.max}"` : ""} placeholder="${c.min ?? "…"}–${c.max ?? "…"}" />
        <span class="muted">${c.min ?? "…"} – ${c.max ?? "…"} ${escapeHtml(c.unit || "")}</span>
        <button type="button" class="btn ghost small" data-frange-ok="${i}">OK</button></div>`;
    } else {
      ctl = `<div class="fill-range"><input data-ftext="${i}" data-fname="${escapeHtml(c.name)}" placeholder="значение" /><button type="button" class="btn ghost small" data-ftext-ok="${i}">OK</button></div>`;
    }
    return `<div class="fill-item ${c.required ? "req" : "opt"}"><span class="fname">${escapeHtml(c.name)}</span>${c.required ? '<span class="req-tag">обязательная</span>' : ' <span class="muted">необязательная</span>'} ${badge(c.source)}${ctl}</div>`;
  };
  return `<div class="block fill" id="fillBlock"><div class="fill-head"><h2>Допишите ещё ${ordered.length} ${plural(ordered.length, "характеристику", "характеристики", "характеристик")}${nReq ? ` <span class="muted">(обязательных: ${nReq})</span>` : ""}</h2>
    ${(() => { const t = fillText(data, filled, total); return t ? `<span class="counter" id="fillCounter">${escapeHtml(t)}</span>` : ""; })()}</div>
    <div class="progress"><i style="width:${pct}%"></i></div>${ordered.map(row).join("")}</div>`;
}
function fillText(data, filled, total) {
  const f = data.fill;
  const clean = (t) => t.replace(/\s*\(\s*обязательных\s+0\s*из\s*0\s*\)/i, "").trim();
  const zero = (t) => /(^|\D)0\s*из\s*0(\D|$)/.test(clean(t));
  if (f && typeof f === "object" && typeof f.text === "string" && !zero(f.text) && f.total !== 0) return clean(f.text) || null;
  if (typeof f === "string" && f.trim() && !zero(f)) return clean(f);
  if (f && typeof f === "object" && f.total === 0) return null;
  if (typeof f === "string" && zero(f)) return null;
  if (f && typeof f === "object" && typeof f.text === "string" && zero(f.text)) return null;
  if (f == null && !total) return null;
  if (typeof f === "string" && f.trim()) return f.trim();
  if (f && typeof f === "object") {
    if (typeof f.text === "string" && f.text.trim()) return f.text.trim();
    if (f.total != null) return `Заполнено ${f.filled ?? 0} из ${f.total}`;
  }
  return `${filled} из ${total}`;
}
function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20) ? few : many;
}
function applyFill(i, name, value) {
  let row = i >= 0 ? state.chars[i] : state.chars.find((c) => norm(c.name) === norm(name));
  if (!row) { row = normChar({ name, value: "", source: "ktru", required: true }); state.chars.push(row); }
  syncText(row, "value", String(row.value ?? ""), value);
  row.value = value;
  markDirty(row);
  clearTimeout(state.timer);
  analyze(true);
}

/* ---------- render ---------- */
function badge(src) {
  return `<span class="badge ${src}">${SOURCE_LABELS[src]}</span>`;
}
function valueEditor(c, i) {
  if (c.allowed) {
    const opts = c.allowed.includes(String(c.value)) || !c.value ? c.allowed : [String(c.value), ...c.allowed];
    return `<select data-i="${i}" data-k="value"><option value=""></option>${opts
      .map((o) => `<option${String(c.value) === o ? " selected" : ""}>${escapeHtml(o)}</option>`)
      .join("")}</select>`;
  }
  const hasRange = c.min !== undefined || c.max !== undefined;
  if (hasRange) {
    return `<input type="number" data-i="${i}" data-k="value" value="${escapeHtml(c.value)}"
      ${c.min !== undefined ? `min="${c.min}"` : ""} ${c.max !== undefined ? `max="${c.max}"` : ""} />
      <div class="hint">допустимо: ${c.min ?? "…"} – ${c.max ?? "…"}${c.unit ? " " + escapeHtml(c.unit) : ""}</div>`;
  }
  return `<input data-i="${i}" data-k="value" value="${escapeHtml(c.value)}" />`;
}
function charsTable(issues) {
  const rowIssue = (c) => issues.find((x) => x.field && norm(x.field) === norm(c.name) && x.type !== "missing");
  const rows = state.chars
    .map((c, i) => {
      const iss = rowIssue(c);
      const emptyReq = c.required && !String(c.value ?? "").trim();
      const cls = (iss ? (iss.severity === "error" ? "err" : "warn") : emptyReq || c.suspicious ? "warn" : "") + (c.suspicious ? " susp" : "");
      return `<tr class="${cls}">
        <td><input data-i="${i}" data-k="name" value="${escapeHtml(c.name)}" placeholder="Название" />
          ${c.suspicious ? `<span class="tag-susp" title="${escapeHtml(iss ? iss.message : "Характеристика не подходит к типу товара")}">подозрительно</span>` : ""}
          ${c.required ? `<div class="hint">обязательная${String(c.value ?? "").trim() ? "" : " · заполните"}</div>` : ""}</td>
        <td class="muted">${escapeHtml(c.user_input)}</td>
        <td>${valueEditor(c, i)}${iss && iss.expected ? `<div class="hint">ожидается: ${escapeHtml(iss.expected)}</div>` : ""}</td>
        <td><input data-i="${i}" data-k="unit" value="${escapeHtml(c.unit)}" style="width:70px" /></td>
        <td>${badge(c.source)}</td>
        <td><button class="del" data-del="${i}" title="Удалить">×</button></td>
      </tr>`;
    })
    .join("");
  return `<table class="chars"><thead><tr><th>Характеристика</th><th>Из текста</th><th>Значение</th><th>Ед.</th><th>Источник</th><th></th></tr></thead>
    <tbody>${rows || `<tr><td colspan="6" class="muted">Характеристики не найдены</td></tr>`}</tbody></table>
    <div style="margin-top:10px"><button class="btn ghost small" id="addRow">+ Добавить характеристику</button></div>`;
}
function issuesBlock(issues) {
  // обязательные, уже есть строкой в таблице (пусть и пустой), не дублируем чипом
  const missing = issues.filter((x) => x.type === "missing" && x.field && !state.chars.some((c) => norm(c.name) === norm(x.field)));
  // out_of_scope уже показан отдельным блоком — в замечаниях не дублируем
  const other = issues.filter((x) => !(x.type === "missing" && x.field) && x.type !== "out_of_scope");
  const missingInTable = issues.filter((x) => x.type === "missing" && x.field && !missing.includes(x)).length;
  const list = other
    .map((x, k) => `<div class="issue ${x.severity === "error" ? "error" : ""}">
      <div>${x.field ? `<b>${escapeHtml(x.field)}:</b> ` : ""}${escapeHtml(x.message)}</div>
      ${x.expected ? `<div class="exp">Ожидается: ${escapeHtml(x.expected)}</div>` : ""}
      ${x.suggestions.length ? `<div class="chips">${x.suggestions
        .map((s) => `<button class="chip" data-sug="${k}" data-val="${escapeHtml(s)}">${escapeHtml(s)}</button>`)
        .join("")}</div>` : ""}
    </div>`)
    .join("");
  const miss = missing.length
    ? `<div class="lbl">Не хватает обязательных характеристик — нажмите, чтобы добавить:</div>
       <div class="chips">${missing
        .map((x) => `<button class="chip add" data-miss="${escapeHtml(x.field)}">+ ${escapeHtml(x.field)}</button>`)
        .join("")}</div>`
    : "";
  const inTable = missingInTable ? `<div class="lbl">Заполните обязательные характеристики в таблице: ${missingInTable}</div>` : "";
  return { html: list + miss + inTable || `<div class="muted">Замечаний нет</div>`, other: other.filter((x) => !(x.type === "missing" && x.field)) };
}
function funnelBlock(steps, candidates) {
  if (!steps.length) return `<div class="muted">Нет данных</div>`;
  const max = Math.max(...steps.map((s) => s.remaining), 1);
  const bars = steps
    .map((s, i) => {
      const w = Math.max(4, Math.round((Math.log10(s.remaining + 1) / Math.log10(max + 1)) * 100));
      const last = i === steps.length - 1;
      return `<div class="bar-row">
        <div class="bar-head"><span>${escapeHtml(s.label)}</span>${s.removed ? `<span class="muted">−${s.removed}</span>` : ""}</div>
        <div class="bar ${last ? "last" : ""}" style="width:${w}%">${s.remaining}</div>
        ${s.reason ? `<div class="reason">${escapeHtml(s.reason)}</div>` : ""}
        ${s.removed_codes.length ? `<div class="reason">исключены: ${s.removed_codes.map(escapeHtml).join(", ")}</div>` : ""}
      </div>`;
    })
    .join("");
  const path = `<div class="muted" style="margin-bottom:10px">${steps.map((s) => s.remaining).join(" → ")}</div>`;
  const cands = candidates.length > 1
    ? `<div class="lbl">Подходящие коды:</div><div class="cand-list">${candidates
        .slice(0, 5)
        .map((c) => `<div class="cand-item"><span class="code">${escapeHtml(c.code)}</span><span>${escapeHtml(c.name)}</span><span class="score">${c.score ?? ""}</span></div>`)
        .join("")}</div>`
    : "";
  return `<div class="funnel">${path}${bars}</div>${cands}`;
}

function render(data) {
  // сменился распознанный товар/домен/топ-код -> правки с именами, которых нет в новом ответе, отбрасываем
  const key = [data.detected_domain || "", data.product_guess || "", data.best_ktru && data.best_ktru.code || ""].join("|");
  if (state.lastKey !== null && key !== state.lastKey && state.dirty.size) {
    const names = new Set((data.characteristics || []).map((c) => norm(c.name || "")));
    for (const k of [...state.dirty.keys()]) if (!names.has(k)) state.dirty.delete(k);
    if (!state.dirty.size) resetOverrides();
  }
  state.lastKey = key;
  state.data = data;
  state.chars = sortBySource((data.characteristics || []).map(normChar));
  // повторно применяем правки пользователя из таблицы поверх ответа
  for (const [key, ov] of state.dirty) {
    const row = state.chars.find((c) => norm(c.name) === key);
    if (row) { row.value = ov.value; row.unit = ov.unit; }
    else state.chars.push(normChar({ ...ov, source: ov.source || "new" }));
  }
  state.chars = sortBySource(state.chars);
  draw();
}
function draw() {
  const data = state.data;
  if (!data) return;
  const active = document.activeElement;
  const focus = active && active.dataset && active.dataset.i !== undefined
    ? { i: active.dataset.i, k: active.dataset.k, pos: active.selectionStart } : null;

  const issues = (data.issues || []).map(normIssue);
  const steps = normSteps(data);
  const candidates = getCandidates(data, steps);
  $("status").className = `status ${data.status || "idle"}`;
  $("status").textContent = statusLabel(data.status);
  const oos = isOutOfScope(data);
  if (oos) { $("status").className = "status error oos"; $("status").textContent = "Не наша категория"; }

  const best = data.best_ktru
    ? `<div class="block product-card" id="productCard"><div class="pc-head"><div class="pc-img">▦</div><div style="flex:1">
       <div class="best"><span class="code">${escapeHtml(data.best_ktru.code)}</span><span class="muted">${data.best_ktru.score ?? ""}</span></div>
       <div class="pc-title">${escapeHtml(data.best_ktru.name)}</div>
       <dl class="pc-props"><dt>Код КТРУ</dt><dd>${escapeHtml(data.best_ktru.code)}</dd>${data.best_ktru.okpd2 ? `<dt>ОКПД2</dt><dd>${escapeHtml(data.best_ktru.okpd2)}</dd>` : ""}<dt>Категория</dt><dd>${escapeHtml(data.detected_domain || "—")}</dd></dl></div></div>
       <div class="muted" style="margin-top:6px">Код КТРУ — это группа товаров; цены на конкретную СТЕ задают поставщики, по ним считается референтная цена.</div></div>`
    : "";
  const ib = issuesBlock(issues);
  const next = nextStepsBlock(data);
  const elapsed = data.debug && data.debug.elapsed_ms != null ? `<span class="muted"> · ${data.debug.elapsed_ms} мс</span>` : "";

  $("result").className = "result";
  $("result").innerHTML = `
    ${oos ? `<div class="block oos-block" id="oosBlock"><span class="sbadge bad">Не наша категория</span> ${escapeHtml(String(data.message || "").replace(/^\s*не наша категория\s*[:.—-]?\s*/i, "") || "Товар не относится к поддерживаемым категориям (мебель, одежда, инструменты). Код КТРУ не подбирается.")}</div>` : ""}
    ${statusBadges(data, issues)}
    <div class="block"><h2>Распознано${elapsed}</h2>
      <div class="muted">Категория: <b>${escapeHtml(data.detected_domain || "—")}</b> · Товар: <b>${escapeHtml(data.product_guess || "—")}</b></div></div>
    ${best}
    ${fillBlock(data, issues)}
    <div class="block"><h2>Характеристики</h2>${charsTable(issues)}${state.dirty.size ? `<div class="hint" id="ovNote">Изменено в таблице: ${state.dirty.size}${state.textNote ? " · правки таблицы имеют приоритет над текстом" : ""} <button class="btn ghost small" id="resetOv">Сбросить правки таблицы</button></div>` : ""}</div>
    ${correctionsBlock(data)}
    <div class="block"><h2>Подсказки</h2>${ib.html}</div>
    <div class="block"><h2>Сужение кодов КТРУ</h2>${funnelBlock(steps, candidates)}</div>
    ${next}`;
  bind(ib.other);
  drawHighlight();

  if (focus) {
    const el = $("result").querySelector(`[data-i="${focus.i}"][data-k="${focus.k}"]`);
    if (el) { el.focus(); try { if (focus.pos != null) el.setSelectionRange(focus.pos, focus.pos); } catch (_) {} }
  }
}
function bind(otherIssues) {
  const root = $("result");
  root.querySelectorAll("[data-k]").forEach((el) => {
    const ev = el.tagName === "SELECT" ? "change" : "input";
    el.addEventListener(ev, () => {
      const row = state.chars[+el.dataset.i];
      const k = el.dataset.k;
      const prev = row[k];
      if (k === "name") {
        state.dirty.delete(norm(prev)); // имя поменяли — старая правка снимается
        row[k] = el.value;
      } else {
        row[k] = el.value;
        syncText(row, k, String(prev ?? ""), String(el.value ?? ""));
        markDirty(row);
      }
      schedule(true);
    });
  });
  root.querySelectorAll("[data-del]").forEach((el) =>
    el.addEventListener("click", () => { state.chars.splice(+el.dataset.del, 1); draw(); schedule(true); }));
  const reset = $("resetOv");
  if (reset) reset.addEventListener("click", () => {
    if (state.origText !== null) $("text").value = state.origText;
    resetOverrides();
    clearTimeout(state.timer); analyze(false); // исходный текст, без characteristics
  });
  root.querySelectorAll("[data-fill]").forEach((el) => el.addEventListener("click", () => applyFill(+el.dataset.fill, el.dataset.fname, el.dataset.fval)));
  const okBtn = (sel, inSel) => root.querySelectorAll(`[${sel}]`).forEach((b) => b.addEventListener("click", () => {
    const inp = root.querySelector(`[${inSel}="${b.getAttribute(sel)}"]`);
    if (inp && inp.value.trim()) applyFill(+b.getAttribute(sel), inp.dataset.fname, inp.value.trim());
  }));
  okBtn("data-frange-ok", "data-frange"); okBtn("data-ftext-ok", "data-ftext");
  root.querySelectorAll("[data-frange],[data-ftext]").forEach((inp) => inp.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && inp.value.trim()) applyFill(+(inp.dataset.frange ?? inp.dataset.ftext), inp.dataset.fname, inp.value.trim());
  }));
  const add = $("addRow");
  if (add) add.addEventListener("click", () => {
    state.chars.push(normChar({ name: "", value: "", source: "new" }));
    draw();
    const inputs = root.querySelectorAll('[data-k="name"]');
    if (inputs.length) inputs[inputs.length - 1].focus();
  });
  root.querySelectorAll("[data-sug]").forEach((el) =>
    el.addEventListener("click", () => {
      const iss = otherIssues[+el.dataset.sug];
      const val = el.dataset.val;
      const row = iss.field ? state.chars.find((c) => norm(c.name) === norm(iss.field)) : null;
      if (row) { syncText(row, "value", String(row.value ?? ""), val); row.value = val; markDirty(row); }
      else if (iss.field) { state.chars.push(normChar({ name: iss.field, value: val, source: "ktru" })); markDirty(state.chars[state.chars.length - 1]); }
      else if (iss.value) $("text").value = $("text").value.replace(iss.value, val);
      draw();
      schedule(true);
    }));
  root.querySelectorAll("[data-miss]").forEach((el) =>
    el.addEventListener("click", () => {
      if (state.chars.some((c) => norm(c.name) === norm(el.dataset.miss))) return;
      state.chars.push(normChar({ name: el.dataset.miss, value: "", source: "ktru", required: true }));
      draw();
      const v = root.querySelectorAll('[data-k="value"]');
      if (v.length) v[v.length - 1].focus();
    }));
}

/* ---------- table -> text sync ---------- */
// Снимок textarea до первой правки таблицы (dirty: пусто -> не пусто).
// Берётся один раз и не обновляется, даже если потом пользователь сам печатал в textarea:
// «Сбросить правки таблицы» всегда возвращает текст, каким он был до правок таблицы.
// Снимок сбрасывается при сбросе правок, выборе демо-кейса и «Очистить».
/* ---------- правило сброса правок таблицы ----------
 * Правки таблицы (state.dirty + снимок state.origText) живут, только пока пользователь
 * правит ТОТ ЖЕ текст. state.baseText — последний текст, который «наш»: результат синхронизации
 * таблицы -> textarea либо текст последнего запроса с сохранёнными правками.
 * Текст считается НОВЫМ, и правки сбрасываются, если:
 *  1) нажата «Проверить» и текст отличается от baseText;
 *  2) вставка (paste/drop) или замена содержимого textarea;
 *  3) при наборе текст стал мало похож на baseText (сходство биграмм Dice < 0.6);
 *  4) выбран демо-кейс или нажато «Очистить».
 * Мелкая правка текста (сходство >= 0.6) правки сохраняет.
 * Дополнительно: если в ответе сменился товар/домен/топ-код, правки с именами,
 * которых нет среди характеристик нового ответа, отбрасываются (см. render). */
const SIM_THRESHOLD = 0.6;
function similarity(a, b) {
  a = norm(a); b = norm(b);
  if (a === b) return 1;
  if (a.length < 2 || b.length < 2) return 0;
  const grams = (s) => { const m = new Map(); for (let i = 0; i < s.length - 1; i++) { const g = s.slice(i, i + 2); m.set(g, (m.get(g) || 0) + 1); } return m; };
  const A = grams(a), B = grams(b); let inter = 0;
  for (const [g, n] of A) inter += Math.min(n, B.get(g) || 0);
  return (2 * inter) / (a.length - 1 + b.length - 1);
}
function resetOverrides() {
  state.dirty.clear(); state.textNote = false; state.origText = null; state.baseText = null;
}
function checkNewText(fromButton) {
  if (!state.dirty.size) { state.baseText = null; return; }
  const cur = $("text").value.trim();
  const base = (state.baseText ?? "").trim();
  if (fromButton ? cur !== base : similarity(cur, base) < SIM_THRESHOLD) resetOverrides();
  else state.baseText = $("text").value; // мелкая правка того же текста -> правки остаются
}
function snapshotText() {
  if (state.origText === null && state.dirty.size === 0) state.origText = $("text").value;
}
function markDirty(row) {
  if (!row.name.trim()) return;
  snapshotText();
  state.dirty.set(norm(row.name), { name: row.name, value: row.value, unit: row.unit, source: row.source });
  state.baseText = $("text").value;
}
// Заменяет фрагмент user_input в textarea («высота 750 мм» -> «высота 900 мм»).
// Программная запись в textarea не порождает событие input, поэтому лишнего пересчёта нет.
function syncText(row, k, prev, next) {
  snapshotText(); // до переписывания textarea
  const frag = row.user_input || "";
  const ta = $("text");
  if (!frag || !prev || prev === next) { if (frag && prev !== next && !prev) state.textNote = true; return; }
  const pos = frag.indexOf(prev);
  const at = ta.value.indexOf(frag);
  if (pos < 0 || at < 0) { state.textNote = true; refreshNote(); return; }
  const newFrag = frag.slice(0, pos) + next + frag.slice(pos + prev.length);
  ta.value = ta.value.slice(0, at) + newFrag + ta.value.slice(at + frag.length);
  row.user_input = newFrag;
  state.baseText = ta.value;
  drawHighlight();
}
function refreshNote() {
  const n = $("ovNote");
  if (n && state.textNote && !n.textContent.includes("приоритет")) {
    n.insertBefore(document.createTextNode(" · правки таблицы имеют приоритет над текстом "), n.querySelector("button"));
  }
}

/* ---------- init ---------- */
async function loadDemos() {
  const res = await fetch("/api/demo-cases");
  const cases = await res.json();
  const box = $("demos");
  box.innerHTML = "";
  cases.forEach((c) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = c.title;
    b.onclick = () => { resetOverrides(); state.lastKey = null; $("text").value = c.text; $("domain").value = c.domain_hint || ""; analyze(false); };
    box.appendChild(b);
  });
}
$("run").onclick = () => { clearTimeout(state.timer); analyze(false, true); };
$("text").addEventListener("input", (e) => {
  const t = e && e.inputType || "";
  if (t === "insertFromPaste" || t === "insertFromDrop" || t === "insertReplacementText") resetOverrides();
  drawHighlight();
  if (!$("text").value.trim()) { showEmpty(); return; }
  schedule(false);
});
$("domain").addEventListener("change", () => schedule(false));
$("clear").onclick = () => {
  clearTimeout(state.timer); state.seq++;
  $("text").value = ""; $("domain").value = "";
  state.data = null; state.chars = []; resetOverrides(); state.lastKey = null;
  $("status").className = "status idle"; $("status").textContent = "Введите описание товара";
  $("result").className = "result empty"; $("result").textContent = "Здесь появится результат проверки";
  drawHighlight();
};
loadDemos().catch(console.error);

/* ---------- вкладки ---------- */
function showTab(tab) {
  document.querySelectorAll(".nav .tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $("viewSingle").classList.toggle("hidden", tab !== "single");
  $("viewBatch").classList.toggle("hidden", tab !== "batch");
  $("crumbLast").textContent = tab === "single" ? "Создание СТЕ" : "Пакетная проверка";
  $("pageTitle").textContent = tab === "single" ? "Создание карточки товара" : "Пакетная проверка наименований";
}
document.querySelectorAll(".nav .tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

/* ---------- пакетная проверка CSV ---------- */
const BATCH_CONCURRENCY = 4;
const batch = { items: [], results: [], mode: null, t0: 0, total_ms: 0, running: false, serverSummary: null };
function decodeCsv(buf) {
  const u8 = new Uint8Array(buf);
  try { return new TextDecoder("utf-8", { fatal: true }).decode(u8).replace(/^\uFEFF/, ""); }
  catch (_) { return new TextDecoder("windows-1251").decode(u8); }
}
// CSV-разбор всего файла с учётом кавычек ("" — экранирование, переводы строк внутри кавычек, CRLF).
function csvRecords(text, delim) {
  const rows = []; let row = [], cur = "", q = false, quoted = false;
  const endRow = () => { row.push(cur); rows.push({ cells: row, quoted }); row = []; cur = ""; quoted = false; };
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) { if (ch === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += ch; continue; }
    if (ch === '"' && cur.trim() === "") { q = true; quoted = true; cur = ""; }
    else if (delim && ch === delim) { row.push(cur); cur = ""; }
    else if (ch === "\r") { if (text[i + 1] === "\n") i++; endRow(); }
    else if (ch === "\n") endRow();
    else cur += ch;
  }
  if (cur !== "" || row.length) endRow();
  return rows;
}
function parseCsvLine(line, delim) { const r = csvRecords(line, delim)[0]; return r ? r.cells : [""]; }
const NAME_COL_RE = /^(наименование|название|наим|name|text|текст|товар|описание|description|title)/i;
// Файл — 1 столбец наименований. Неэкранированные «;» и «,» — часть описания.
// Несколько столбцов — только если заголовок явно их объявляет; тогда берём столбец наименования.
function parseNames(text) {
  text = String(text || "").replace(/^\uFEFF/, "");
  const firstLine = (text.split(/\r?\n/).find((l) => l.trim()) || "").trim();
  let delim = null, col = 0, skipHeader = false;
  for (const d of [";", ",", "\t"]) {
    if (!firstLine.includes(d)) continue;
    const cells = parseCsvLine(firstLine, d).map((c) => c.trim());
    const idx = cells.findIndex((c) => NAME_COL_RE.test(c) && c.length < 40);
    const headerLike = cells.length > 1 && idx >= 0 && cells.every((c) => c.length < 40 && !/\d{2,}/.test(c));
    if (headerLike) { delim = d; col = idx; skipHeader = true; break; }
  }
  const recs = csvRecords(text, delim);
  let names = recs.map((r, i) => {
    if (delim) return (r.cells[col] || "").trim();
    // одна колонка: если строка в кавычках — значение из кавычек (+ хвост), иначе строка целиком
    return r.cells.join("").trim();
  });
  if (skipHeader) names = names.slice(1);
  else if (names.length && NAME_COL_RE.test(names[0]) && names[0].length < 40 && !/\d/.test(names[0])) names = names.slice(1);
  return names.filter(Boolean);
}
function summarize(results) {
  const s = { total: results.length, determined: 0, ambiguous: 0, not_found: 0, out_of_scope: 0, complete: 0, incomplete: 0, invalid: 0, errors: 0 };
  for (const r of results) {
    if (!r) continue;
    if (r.error) { s.errors++; continue; }
    s[r.code_status] = (s[r.code_status] || 0) + 1;
    s[r.card_status] = (s[r.card_status] || 0) + 1;
  }
  return s;
}
const isOutOfScope = (d) => !!(d && (d.out_of_scope || d.not_our_category || d.in_scope === false || d.scope === "out" || d.code_status === "out_of_scope"));
function rowView(id, text, data, ms) {
  if (!data || data.error) return { id, text, error: data ? data.error : "нет ответа", ms };
  const issues = (data.issues || []).map(normIssue);
  const save = state.chars; state.chars = (data.characteristics || []).map(normChar);
  const comp = completenessOf(data);
  const card = cardStatus(data, issues, comp);
  state.chars = save;
  const chars = sortBySource((data.characteristics || []).map(normChar));
  return {
    id, text, data, ms: Math.round(data.debug && data.debug.elapsed_ms != null ? data.debug.elapsed_ms : ms),
    code: data.best_ktru ? data.best_ktru.code : "", name: data.best_ktru ? data.best_ktru.name : "",
    code_status: isOutOfScope(data) ? "out_of_scope" : codeStatus(data), card_status: card, out_of_scope: isOutOfScope(data),
    missing: Math.max(0, (comp.required_total || 0) - (comp.required_filled || 0)),
    notes: issues.filter((x) => x.type !== "missing").map((x) => (x.field ? x.field + ": " : "") + x.message).join("; "),
    chars: chars.filter(isFilled).map((c) => `${c.name}=${c.value}${c.unit ? " " + c.unit : ""}`).join("; "),
  };
}
CODE_LABELS.out_of_scope = "не наша категория";
const CARD_LABELS = { complete: "заполнена", incomplete: "неполная", invalid: "есть ошибки" };
function drawBatchRow(i) {
  const r = batch.results[i];
  const tr = $("batchBody").children[i];
  if (!tr || !r) return;
  const cls = (v) => (v === "determined" || v === "complete" ? "good" : v === "not_found" || v === "invalid" ? "bad" : "mid");
  tr.innerHTML = r.error
    ? `<td class="num">${i + 1}</td><td>${escapeHtml(r.text)}</td><td colspan="6" class="muted">Ошибка: ${escapeHtml(r.error)}</td><td>${r.ms ?? ""}</td>`
    : `<td class="num">${i + 1}</td><td>${escapeHtml(r.text)}</td><td class="code">${escapeHtml(r.code || "—")}</td><td>${escapeHtml(r.name)}</td>
      <td><span class="sbadge ${cls(r.code_status)}">${CODE_LABELS[r.code_status]}</span></td>
      <td><span class="sbadge ${cls(r.card_status)}">${CARD_LABELS[r.card_status]}</span></td>
      <td>${r.missing}</td><td class="muted">${escapeHtml(r.notes)}</td><td>${r.ms ?? ""} мс</td>`;
}
function drawSummary(done) {
  const s = summarize(batch.results);
  const n = batch.results.filter(Boolean).length;
  $("pbar").style.width = (batch.items.length ? Math.round((n / batch.items.length) * 100) : 0) + "%";
  $("progressText").textContent = `Обработано ${n} из ${batch.items.length}` + (done ? ` · общее время ${batch.total_ms} мс` : "");
  $("summary").innerHTML = `<span class="sbadge mid" id="sumTotal">Всего: ${s.total}</span>
    <span class="sbadge good">Код определён: ${s.determined}</span><span class="sbadge mid">Несколько вариантов: ${s.ambiguous}</span><span class="sbadge bad">Не найден: ${s.not_found}</span><span class="sbadge mid" id="sumOos">Не наша категория: ${s.out_of_scope}</span>
    <span class="sbadge good">Заполнена: ${s.complete}</span><span class="sbadge mid">Неполная: ${s.incomplete}</span><span class="sbadge bad">С ошибками: ${s.invalid}</span>
    ${s.errors ? `<span class="sbadge bad">Сбой запроса: ${s.errors}</span>` : ""}${done ? `<span class="sbadge mid" id="sumTime">Время: ${batch.total_ms} мс</span>` : ""}`;
}
async function analyzeOne(text) {
  const t = performance.now();
  try {
    const res = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    const data = await res.json();
    if (!res.ok) return [{ error: typeof data.detail === "string" ? data.detail : "HTTP " + res.status }, Math.round(performance.now() - t)];
    return [data, Math.round(performance.now() - t)];
  } catch (e) { return [{ error: e.message }, Math.round(performance.now() - t)]; }
}
// Возможности пакетного API: один тихий запрос к /openapi.json, без обращений к несуществующим путям.
let batchCapsPromise = null;
function batchCaps() {
  if (!batchCapsPromise) batchCapsPromise = (async () => {
    try {
      const res = await fetch("/openapi.json", { cache: "no-store" });
      if (!res.ok) return { batch: false, stream: false };
      const spec = await res.json();
      const op = spec && spec.paths && spec.paths["/api/analyze/batch"] && spec.paths["/api/analyze/batch"].post;
      if (!op) return { batch: false, stream: false };
      const blob = JSON.stringify(op).toLowerCase();
      const stream = (op.parameters || []).some((p) => p && p.name === "stream") || /ndjson|stream/.test(blob);
      return { batch: true, stream };
    } catch (_) { return { batch: false, stream: false }; }
  })();
  return batchCapsPromise;
}
async function runBatch(names) {
  if (batch.running) return;
  batch.running = true;
  batch.items = names.map((text, i) => ({ id: String(i + 1), text }));
  batch.results = new Array(names.length).fill(null); batch.serverSummary = null;
  $("exportCsv").disabled = true;
  $("batchBody").innerHTML = batch.items.map((it, i) => `<tr data-row="${i}"><td class="num">${i + 1}</td><td>${escapeHtml(it.text)}</td><td colspan="7" class="muted">ожидает…</td></tr>`).join("");
  drawSummary(false);
  batch.t0 = performance.now();
  const put = (d, k) => {
    const idx = d && d.id != null ? batch.items.findIndex((x) => x.id === String(d.id)) : k;
    const i = idx >= 0 ? idx : k;
    if (i < 0 || i >= batch.items.length || batch.results[i]) return;
    batch.results[i] = rowView(batch.items[i].id, batch.items[i].text, d && (d.result || d), null);
    drawBatchRow(i); drawSummary(false);
  };
  const payload = JSON.stringify({ items: batch.items.slice(0, 500) });
  let ok = false;
  batch.mode = "per-row";
  const caps = await batchCaps();
  if (caps.batch && batch.items.length <= 500) {
    // 1) потоковый ответ NDJSON: строка на позицию, последняя — summary
    if (caps.stream) try {
      const res = await fetch("/api/analyze/batch?stream=1", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload });
      if (res.ok && res.body && res.body.getReader) {
        const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "", k = 0, any = false;
        const line = (l) => { l = l.trim(); if (!l) return; let o; try { o = JSON.parse(l); } catch (_) { return; }
          if ((o.type === "summary" || o.summary) && !o.result && o.id == null && !o.characteristics) { batch.serverSummary = o.summary || o; return; } any = true; put(o, k++); };
        for (;;) { const { value, done } = await reader.read(); if (done) break; buf += dec.decode(value, { stream: true });
          let nl; while ((nl = buf.indexOf("\n")) >= 0) { line(buf.slice(0, nl)); buf = buf.slice(nl + 1); } }
        line(buf);
        if (any) { ok = true; batch.mode = "stream"; }
      } else if (res.ok) {
        const txt = await res.text(); let k = 0;
        txt.split("\n").forEach((l) => { try { const o = JSON.parse(l); if (!(o.summary && o.id == null && !o.result)) { put(o, k++); ok = true; } } catch (_) {} });
        if (ok) batch.mode = "stream";
      }
    } catch (_) { ok = false; }
    // 2) обычный пакетный ответ {results, summary}
    if (!ok) {
      try {
        const res = await fetch("/api/analyze/batch", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload });
        if (res.ok) { const body = await res.json(); if (Array.isArray(body.results)) { batch.serverSummary = body.summary || null; body.results.forEach(put); ok = true; batch.mode = "batch"; } }
      } catch (_) { ok = false; }
    }
  }
  $("batchMode").textContent = { stream: "Режим: потоковый API /api/analyze/batch?stream=1", batch: "Режим: пакетный API /api/analyze/batch" }[batch.mode]
    || `Режим: построчно через /api/analyze (параллельно ${BATCH_CONCURRENCY})`;
  if (!ok) {
    let next = 0;
    const worker = async () => {
      while (next < batch.items.length) {
        const i = next++;
        if (batch.results[i]) continue;
        const [data, ms] = await analyzeOne(batch.items[i].text);
        batch.results[i] = rowView(batch.items[i].id, batch.items[i].text, data, ms);
        drawBatchRow(i);
        drawSummary(false);
      }
    };
    await Promise.all(Array.from({ length: Math.min(BATCH_CONCURRENCY, batch.items.length) }, worker));
  }
  batch.total_ms = Math.round(performance.now() - batch.t0);
  drawSummary(true);
  $("exportCsv").disabled = false;
  batch.running = false;
}
const csvCell = (v) => { const s = String(v ?? ""); return /[";,\n\r]/.test(s) ? '"' + s.replaceAll('"', '""') + '"' : s; };
function buildExportCsv() {
  const head = ["№", "Исходный текст", "Код КТРУ", "Наименование", "Статус кода", "Статус карточки", "Не хватает обязательных", "Замечания", "Время, мс", "Характеристики"];
  const lines = [head.join(";")];
  batch.results.forEach((r, i) => {
    if (!r) return;
    lines.push((r.error
      ? [i + 1, r.text, "", "", "ошибка", "", "", r.error, r.ms ?? "", ""]
      : [i + 1, r.text, r.code, r.name, CODE_LABELS[r.code_status], CARD_LABELS[r.card_status], r.missing, r.notes, r.ms ?? "", r.chars]).map(csvCell).join(";"));
  });
  return "\uFEFF" + lines.join("\r\n") + "\r\n";
}
$("exportCsv").addEventListener("click", () => {
  const blob = new Blob([buildExportCsv()], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ktru_batch_result.csv";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});
async function handleFile(file) {
  if (!file) return;
  const names = parseNames(decodeCsv(await file.arrayBuffer()));
  if (!names.length) { $("progressText").textContent = "В файле не найдено наименований"; return; }
  await runBatch(names);
}
$("csvFile").addEventListener("change", (e) => handleFile(e.target.files[0]));
$("pick").addEventListener("click", (e) => { e.preventDefault(); $("csvFile").click(); });
const drop = $("drop");
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => handleFile(e.dataTransfer && e.dataTransfer.files[0]));
$("batchBody").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-row]");
  if (!tr) return;
  const r = batch.results[+tr.dataset.row];
  if (!r) return;
  showTab("single");
  clearTimeout(state.timer); resetOverrides(); state.lastKey = null;
  $("text").value = r.text; $("domain").value = "";
  analyze(false);
});
window.__ktru = { batch, batchCaps, csvRecords, parseNames, decodeCsv, buildExportCsv, handleFile, runBatch, showTab, state };
