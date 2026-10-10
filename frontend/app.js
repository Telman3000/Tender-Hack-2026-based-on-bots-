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
  if (!text) return;
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
    <div class="muted small" id="complLine">${comp.required_filled}/${comp.required_total} обязательных, ${comp.optional_filled}/${comp.optional_total} необязательных</div>`;
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
      const cls = iss ? (iss.severity === "error" ? "err" : "warn") : emptyReq ? "warn" : "";
      return `<tr class="${cls}">
        <td><input data-i="${i}" data-k="name" value="${escapeHtml(c.name)}" placeholder="Название" />
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
  const other = issues.filter((x) => !(x.type === "missing" && x.field));
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
  state.chars = (data.characteristics || []).map(normChar);
  // повторно применяем правки пользователя из таблицы поверх ответа
  for (const [key, ov] of state.dirty) {
    const row = state.chars.find((c) => norm(c.name) === key);
    if (row) { row.value = ov.value; row.unit = ov.unit; }
    else state.chars.push(normChar({ ...ov, source: ov.source || "new" }));
  }
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

  const best = data.best_ktru
    ? `<div class="block"><h2>Код КТРУ</h2><div class="best"><span class="code">${escapeHtml(data.best_ktru.code)}</span><span class="muted">${data.best_ktru.score ?? ""}</span></div>
       <div><b>${escapeHtml(data.best_ktru.name)}</b></div>
       ${data.best_ktru.okpd2 ? `<div class="muted">ОКПД2: ${escapeHtml(data.best_ktru.okpd2)}</div>` : ""}
       <div class="muted" style="margin-top:6px">Код КТРУ — это группа товаров; цены на конкретную СТЕ задают поставщики, по ним считается референтная цена.</div></div>`
    : "";
  const ib = issuesBlock(issues);
  const next = nextStepsBlock(data);
  const elapsed = data.debug && data.debug.elapsed_ms != null ? `<span class="muted"> · ${data.debug.elapsed_ms} мс</span>` : "";

  $("result").className = "result";
  $("result").innerHTML = `
    ${statusBadges(data, issues)}
    <div class="block"><h2>Распознано${elapsed}</h2>
      <div class="muted">Категория: <b>${escapeHtml(data.detected_domain || "—")}</b> · Товар: <b>${escapeHtml(data.product_guess || "—")}</b></div></div>
    ${best}
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
