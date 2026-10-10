"use strict";
const $ = (id) => document.getElementById(id);
const DEBOUNCE_MS = 600;
const HISTORY_LIMIT = 50;
const DOMAINS = { furniture: "мебель", clothing: "одежда", tools: "инструменты" };
const ORIGINS = { ktru: "КТРУ", portal: "Портал", new: "дополнение" };
const MATCH = {
  MATCHED: ["код определён", "good"],
  NEEDS_CLARIFICATION: ["нужно уточнение", "mid"],
  INPUT_CONFLICT: ["противоречие во вводе", "bad"],
  NO_MATCH_IN_SNAPSHOT: ["нет совпадения в снимке КТРУ", "bad"],
};
const CARD = {
  READY: ["готова", "good"],
  INCOMPLETE: ["неполная", "mid"],
  HAS_UNVERIFIED_EXTRAS: ["есть непроверенные дополнения", "extra"],
};
const KINDS = { unit: "единицы", autofix: "автоисправление", typo: "опечатка", translit: "транслит" };
const FIXABLE = new Set(["typo", "autofix", "translit"]);

const state = {
  data: null,
  chars: [],
  seq: 0,
  timer: null,
  over: new Map(),
  overText: null,
  history: [],
  done: null,
  restoring: null,
  focus: null,
  answer: null,
  prevSearch: null,
};

const esc = (s) => String(s ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const norm = (s) => String(s ?? "").trim().toLowerCase().replaceAll("ё", "е");
const filled = (c) => String(c.value ?? "").trim() !== "";
const withUnit = (c) => [c.value, c.unit].filter((x) => String(x ?? "").trim()).join(" ");

function spanOf(x) {
  const s = x && x.span;
  if (Array.isArray(s) && s.length >= 2) return { start: +s[0], end: +s[1] };
  if (s && s.start != null && s.end != null) return { start: +s.start, end: +s.end };
  return null;
}
function normChar(c) {
  const allowed = c.allowed_values || c.allowed || null;
  const known = (v) => v === "ktru" || v === "portal" || v === "new";
  return {
    name: c.name || c.canonical_name || "",
    user_input: c.user_input || "",
    value: c.value ?? "",
    unit: c.unit ?? "",
    origin: known(c.origin) ? c.origin : known(c.source) ? c.source : "new",
    required: !!c.required,
    allowed: Array.isArray(allowed) && allowed.length ? allowed.map(String) : null,
    min: c.min ?? undefined,
    max: c.max ?? undefined,
    span: spanOf(c),
    polarity: c.polarity || "positive",
    edited: false,
  };
}
function normIssue(i) {
  let suggestions = Array.isArray(i.suggestions) ? i.suggestions : [];
  if (!suggestions.length && i.suggestion) suggestions = [i.suggestion];
  const type = i.type || i.kind || "warning";
  return {
    type,
    field: i.field ?? null,
    value: i.value ?? "",
    expected: i.expected ?? "",
    suggestions: suggestions.slice(0, 3).map(String),
    message: i.message || "",
    severity: i.severity || (type === "missing" ? "warning" : "error"),
    span: spanOf(i),
  };
}
function normSteps(data) {
  return (data.narrowing || []).map((s, k) => ({
    label: s.label || s.stage || `Шаг ${k + 1}`,
    remaining: Number(s.remaining) || 0,
    removed: Number(s.removed) || 0,
    reason: s.reason || s.note || "",
  }));
}

function matchOf(d) {
  if (MATCH[d.match_status]) return d.match_status;
  if (d.status === "ok") return "MATCHED";
  if (d.status === "not_found") return "NO_MATCH_IN_SNAPSHOT";
  if ((d.issues || []).some((i) => String(i.message || "").startsWith("INPUT_CONFLICT"))) return "INPUT_CONFLICT";
  return "NEEDS_CLARIFICATION";
}
function cardOf(d) {
  if (CARD[d.card_status]) return d.card_status;
  if (d.card_status === "complete") return "READY";
  if (d.card_status === "incomplete" || d.card_status === "invalid") return "INCOMPLETE";
  if (state.chars.some((c) => c.required && !filled(c))) return "INCOMPLETE";
  if (state.chars.some((c) => c.origin === "new" && filled(c))) return "HAS_UNVERIFIED_EXTRAS";
  return "READY";
}
function searchOf(d, steps) {
  const s = d.search;
  if (s && (s.area_size || s.compatible_count || s.checked_count)) {
    return { area: s.area_size, checked: s.checked_count, compatible: s.compatible_count, full: s.completeness === "full", domain: s.domain || d.detected_domain };
  }
  if (!steps.length) return null;
  return { area: steps[0].remaining, checked: null, compatible: steps[steps.length - 1].remaining, full: false, domain: d.detected_domain };
}

function snapshot() {
  return {
    text: $("text").value.trim(),
    domain: $("domain").value,
    over: [...state.over.values()].map((o) => ({ name: o.name, value: String(o.value ?? ""), unit: o.unit || "" })),
  };
}
function sameSnap(a, b) {
  return !!a && !!b && a.text === b.text && a.domain === b.domain && JSON.stringify(a.over) === JSON.stringify(b.over);
}
function similarity(a, b) {
  a = norm(a); b = norm(b);
  if (a === b) return 1;
  if (a.length < 2 || b.length < 2) return 0;
  const grams = (s) => { const m = new Map(); for (let i = 0; i < s.length - 1; i++) { const g = s.slice(i, i + 2); m.set(g, (m.get(g) || 0) + 1); } return m; };
  const A = grams(a), B = grams(b);
  let common = 0;
  for (const [g, n] of A) common += Math.min(n, B.get(g) || 0);
  return (2 * common) / (a.length + b.length - 2);
}
function dropOverrides() {
  state.over.clear();
  state.overText = null;
}

function schedule() {
  clearTimeout(state.timer);
  state.timer = setTimeout(analyze, DEBOUNCE_MS);
}
function setBusy(on) {
  const res = $("result");
  res.classList.toggle("stale", on && !!state.data);
  res.setAttribute("aria-busy", on ? "true" : "false");
  if (on) {
    $("status").className = "status busy";
    $("status").textContent = "Проверяем…";
  }
}
async function health() {
  try {
    const r = await fetch("/api/health", { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch (_) {
    return null;
  }
}
function looksLikeDbFailure(d) {
  const noSearch = !(d.search && d.search.area_size) && !(d.narrowing || []).length;
  return noSearch && (d.match_status === "NO_MATCH_IN_SNAPSHOT" || d.status === "error" || d.status === "not_found");
}
async function analyze() {
  clearTimeout(state.timer);
  if (state.over.size && state.overText !== null && similarity($("text").value, state.overText) < 0.5) dropOverrides();
  const snap = snapshot();
  if (!snap.text) return;
  const seq = ++state.seq;
  setBusy(true);
  const body = { text: snap.text, domain_hint: snap.domain || null };
  if (snap.over.length) body.characteristics = snap.over.map((o) => ({ name: o.name, value: o.value, unit: o.unit || null }));
  let data = null, problem = null;
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    data = await res.json().catch(() => null);
    if (!res.ok || !data) problem = data && typeof data.detail === "string" ? data.detail : `сервер ответил ${res.status}`;
  } catch (_) {
    problem = "сервер не отвечает";
  }
  if (!problem && looksLikeDbFailure(data)) {
    const h = await health();
    if (!h || !h.db_ready) problem = "база КТРУ не загружена";
  }
  if (seq !== state.seq || !sameSnap(snap, snapshot())) return;
  setBusy(false);
  if (problem) {
    showTech(problem);
    return;
  }
  commit(snap);
  render(data);
  followAnswer();
}

function commit(snap) {
  if (state.restoring && sameSnap(state.restoring, snap)) state.restoring = null;
  else if (state.done && !sameSnap(state.done, snap)) state.history.push(state.done);
  state.restoring = null;
  if (state.history.length > HISTORY_LIMIT) state.history.shift();
  state.done = snap;
  refreshUndo();
}
function refreshUndo() {
  const btn = $("undo");
  const prev = state.history[state.history.length - 1];
  btn.disabled = !prev;
  btn.title = prev ? `Вернуть: «${prev.text}»` : "";
}
function undo() {
  const prev = state.history.pop();
  refreshUndo();
  if (!prev) return;
  $("text").value = prev.text;
  $("domain").value = prev.domain;
  state.over = new Map(prev.over.map((o) => [norm(o.name), { ...o }]));
  state.overText = state.over.size ? prev.text : null;
  state.answer = null;
  state.restoring = prev;
  analyze();
}

function showTech(message) {
  state.data = null;
  state.chars = [];
  state.focus = null;
  $("source").hidden = true;
  $("status").className = "status tech";
  $("status").textContent = `Техническая ошибка: ${message}`;
  $("result").className = "result";
  $("result").innerHTML = `<div class="summary" id="summary"><div class="sbadges">
      <span class="sbadge bad" id="matchBadge" data-status="TECHNICAL_ERROR"><span class="cap">Подбор</span>техническая ошибка</span>
      <span class="sbadge off" id="cardBadge" data-status="NOT_CHECKED"><span class="cap">Карточка</span>не проверена</span></div></div>
    <div class="block tech" id="techError"><h2>Сервис не смог выполнить проверку</h2>
      <div>${esc(message)}.</div>
      <div class="muted">Это сбой сервиса, а не результат поиска: про наличие кода КТРУ ничего не известно. Повторите запрос; если ошибка повторяется, проверьте, что база собрана и сервер запущен.</div></div>`;
}

function render(data) {
  if (state.data && state.data.search) state.prevSearch = { text: state.data.input_text, ...state.data.search };
  state.data = data;
  state.chars = (data.characteristics || []).map(normChar);
  const src = String(data.input_text ?? "");
  for (const c of state.chars) if (!c.span && c.user_input) c.span = findSpan(src, c.user_input);
  for (const o of state.over.values()) {
    const row = state.chars.find((c) => norm(c.name) === norm(o.name));
    if (row) { row.value = o.value; row.unit = o.unit; row.edited = true; }
  }
  if (state.focus && !state.chars.some((c) => norm(c.name) === state.focus)) state.focus = null;
  draw();
}

function findSpan(text, frag) {
  const low = text.toLowerCase();
  for (const f of new Set([frag, frag.replace(/(\d)\.(\d)/g, "$1,$2"), frag.replace(/(\d),(\d)/g, "$1.$2")])) {
    const at = low.indexOf(f.toLowerCase());
    if (at >= 0) return { start: at, end: at + f.length };
  }
  return null;
}

function followAnswer() {
  const a = state.answer;
  state.answer = null;
  if (!a || !state.data) return;
  const field = norm(a.field), option = norm(a.option).replace(",", ".");
  const got = state.chars.some((c) => {
    const n = norm(c.name);
    return (n === field || n.startsWith(field) || field.startsWith(n)) && norm(c.value).replace(",", ".") === option;
  });
  if (got) return;
  if (!state.over.size) state.overText = $("text").value;
  state.over.set(field, { name: a.field, value: a.option, unit: "" });
  analyze();
}

function answer(field, option) {
  const name = field.replace(/\s*\([^)]*\)/g, "").trim() || field;
  const value = /^\d+,\d+$/.test(option) ? option.replace(",", ".") : option;
  const ta = $("text");
  ta.value = `${ta.value.replace(/[\s,.;]+$/, "")}, ${name}: ${value}`;
  state.answer = { field, option };
  analyze();
}

function textMatchesData() {
  return !!state.data && $("text").value.trim() === String(state.data.input_text ?? "").trim();
}
function tidy(text) {
  return text
    .replace(/\s+([,.;])/g, "$1")
    .replace(/([,;])(\s*[,;])+/g, "$1")
    .replace(/\s{2,}/g, " ")
    .replace(/^[\s,;.]+|[\s,;]+$/g, "");
}
function cutSpans(spans) {
  if (!textMatchesData()) return false;
  let text = String(state.data.input_text);
  for (const s of [...spans].sort((a, b) => b.start - a.start)) text = text.slice(0, s.start) + text.slice(s.end);
  $("text").value = tidy(text);
  return true;
}
function keepValue(group, keep) {
  if (cutSpans(group.filter((c) => c !== keep).map((c) => c.span))) analyze();
}
function applyFix(c) {
  if (!textMatchesData() || !c.span) return;
  const text = String(state.data.input_text);
  const from = text.slice(c.span.start, c.span.end);
  let to = c.to;
  if (from[0] && from[0] !== from[0].toLowerCase()) to = to.charAt(0).toUpperCase() + to.slice(1);
  $("text").value = text.slice(0, c.span.start) + to + text.slice(c.span.end);
  analyze();
}

function conflictGroups() {
  const by = new Map();
  for (const c of state.chars) {
    if (!c.span || !filled(c) || c.polarity === "negative") continue;
    const k = norm(c.name);
    if (!by.has(k)) by.set(k, []);
    by.get(k).push(c);
  }
  return [...by.values()].filter((g) => new Set(g.map((c) => `${norm(c.value)}|${norm(c.unit)}`)).size > 1);
}
function correctionsList(data) {
  const src = String(data.input_text ?? "");
  return (data.corrections || [])
    .map((c) => ({ field: c.field || "", kind: c.kind || "", from: String(c.from ?? c.from_ ?? ""), to: String(c.to ?? ""), span: spanOf(c) }))
    .filter((c) => c.from && c.from !== c.to)
    .map((c) => ({ ...c, fixable: FIXABLE.has(c.kind) && !!c.span && norm(src.slice(c.span.start, c.span.end)) === norm(c.from) }));
}

function badgesBlock(data, match, card, search, steps) {
  const missing = state.chars.filter((c) => c.required && !filled(c)).length;
  const extras = state.chars.filter((c) => c.origin === "new" && filled(c)).length;
  const errors = (data.issues || []).map(normIssue).filter((i) => i.severity === "error").length;
  let cardNote = "";
  if (card === "INCOMPLETE") cardNote = missing ? ` · не заполнено обязательных: ${missing}` : errors ? ` · ошибок: ${errors}` : "";
  if (card === "HAS_UNVERIFIED_EXTRAS" && extras) cardNote = `: ${extras}`;
  const counters = search ? countersBlock(search, data) : "";
  return `<div class="summary" id="summary"><div class="sbadges">
      <span class="sbadge ${MATCH[match][1]}" id="matchBadge" data-status="${match}"><span class="cap">Подбор</span>${MATCH[match][0]}</span>
      <span class="sbadge ${CARD[card][1]}" id="cardBadge" data-status="${card}"><span class="cap">Карточка</span>${CARD[card][0]}${cardNote}</span>
    </div>${counters}</div>`;
}
function countersBlock(s, data) {
  const prev = state.prevSearch;
  const related = prev && (norm(data.input_text).includes(norm(prev.text)) || norm(prev.text).includes(norm(data.input_text)) || similarity(prev.text, data.input_text) >= 0.6);
  const was = (old, now) => (related && old != null && now != null && old !== now && prev.area_size === s.area
    ? `<span class="was-num" title="В предыдущем ответе">было ${old}</span>` : "");
  const domain = DOMAINS[s.domain] || "все категории";
  return `<div class="counters" id="counters">
      <div class="counter"><b id="areaSize">${s.area ?? "—"}</b><span>в области поиска · ${esc(domain)}</span></div>
      <div class="counter"><b id="checkedCount">${s.checked ?? "—"}</b><span>проверено по характеристикам</span>${was(prev && prev.checked_count, s.checked)}</div>
      <div class="counter ok"><b id="compatibleCount">${s.compatible ?? "—"}</b><span>совместимы</span>${was(prev && prev.compatible_count, s.compatible)}</div>
    </div>`;
}

function actionBlock(data, match) {
  if (match === "INPUT_CONFLICT") {
    const groups = conflictGroups();
    const issues = (data.issues || []).map(normIssue).filter((i) => i.message.startsWith("INPUT_CONFLICT"));
    const body = groups.length
      ? groups.map((g, k) => `<div class="conflict-row"><div><b>${esc(g[0].name)}</b>: в описании ${g.length} разных значения</div>
          <div class="chips">${g.map((c, j) => `<button class="chip" type="button" data-keep="${k}:${j}">Оставить ${esc(withUnit(c))}</button>`).join("")}</div></div>`).join("")
      : issues.map((i) => `<div>${esc(i.message.replace(/^INPUT_CONFLICT:\s*/, ""))}</div>`).join("");
    return `<div class="block conflict" id="conflict"><h2>Противоречие во вводе</h2>
      <div class="muted">Подбор кода остановлен: пока одно и то же свойство задано разными значениями, код выбрать нельзя.</div>${body}</div>`;
  }
  if (match === "NO_MATCH_IN_SNAPSHOT") {
    const s = data.search || {};
    const full = s.completeness === "full";
    return `<div class="block nomatch" id="noMatch"><h2>Совместимых кодов нет</h2>
      <div>${full ? `Проверена вся область поиска (${s.area_size} позиций): ни один код КТРУ не совместим с введёнными значениями.` : "В снимке КТРУ не нашлось позиции для этого описания."}</div>
      <div class="muted">Причины отсева — в блоке «Подбор кода КТРУ» ниже. Исправьте значение или уберите лишнее свойство.</div></div>`;
  }
  const q = data.question;
  if (!q || !q.field || !(q.options || []).length) return "";
  const n = data.search ? data.search.compatible_count : null;
  return `<div class="block question" id="question"><h2>Уточняющий вопрос</h2>
    <div class="q-field">${esc(q.field)}</div>
    ${q.reason ? `<div class="muted">${esc(q.reason)}</div>` : ""}
    <div class="chips">${q.options.map((o, k) => `<button class="chip answer" type="button" data-answer="${k}">${esc(o)}</button>`).join("")}</div>
    <div class="hint">Ответ допишется в описание${n != null ? ` · сейчас совместимы ${n}` : ""}</div></div>`;
}

function bestBlock(data, match) {
  const b = data.best_ktru;
  if (!b || match === "INPUT_CONFLICT" || match === "NO_MATCH_IN_SNAPSHOT") return "";
  const title = match === "MATCHED" ? "Код КТРУ" : "Предварительный код КТРУ";
  return `<div class="block" id="best"><h2>${title}</h2>
    <div class="best"><span class="code">${esc(b.code)}</span>${b.okpd2 ? `<span class="muted">ОКПД2 ${esc(b.okpd2)}</span>` : ""}</div>
    <div class="best-name">${esc(b.name)}</div>
    ${match === "MATCHED" ? "" : `<div class="muted">Код станет окончательным после уточнения.</div>`}</div>`;
}

function valueEditor(c, i) {
  if (c.allowed) {
    const opts = c.allowed.includes(String(c.value)) || !filled(c) ? c.allowed : [String(c.value), ...c.allowed];
    return `<select data-i="${i}" data-k="value"><option value=""></option>${opts
      .map((o) => `<option${String(c.value) === o ? " selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
  }
  if (c.min !== undefined || c.max !== undefined) {
    return `<input type="number" step="any" data-i="${i}" data-k="value" value="${esc(c.value)}"
      ${c.min !== undefined ? `min="${c.min}"` : ""} ${c.max !== undefined ? `max="${c.max}"` : ""} />
      <div class="hint">допустимо: ${c.min ?? "…"} – ${c.max ?? "…"}${c.unit ? " " + esc(c.unit) : ""}</div>`;
  }
  return `<input data-i="${i}" data-k="value" value="${esc(c.value)}" />`;
}
function charRow(c, i, issues) {
  const iss = issues.find((x) => x.field && norm(x.field) === norm(c.name) && x.type !== "missing");
  const emptyReq = c.required && !filled(c);
  const cls = [iss ? (iss.severity === "error" ? "err" : "warn") : emptyReq ? "warn" : "", state.focus === norm(c.name) ? "active" : ""].join(" ").trim();
  const notes = [];
  if (c.required) notes.push(filled(c) ? "обязательная" : "обязательная · заполните");
  if (c.edited) notes.push("задано в таблице");
  if (c.polarity === "negative") notes.push("указано с отрицанием");
  const canDelete = !!c.span || c.edited;
  return `<tr class="${cls}" data-row="${i}" data-name="${esc(norm(c.name))}">
      <td class="name"><span class="char-name">${esc(c.name)}</span>${notes.length ? `<div class="hint">${notes.join(" · ")}</div>` : ""}</td>
      <td class="muted from">${esc(c.user_input)}</td>
      <td>${valueEditor(c, i)}${iss && iss.expected ? `<div class="hint">ожидается: ${esc(iss.expected)}</div>` : ""}</td>
      <td><input class="unit" data-i="${i}" data-k="unit" value="${esc(c.unit)}" /></td>
      <td><span class="badge ${c.origin}">${ORIGINS[c.origin]}</span></td>
      <td>${canDelete ? `<button class="del" type="button" data-del="${i}" title="Убрать из описания">×</button>` : ""}</td>
    </tr>`;
}
function charsBlock(issues) {
  const rows = state.chars.map((c, i) => (c.origin === "new" ? "" : charRow(c, i, issues))).join("");
  const edited = state.over.size
    ? `<div class="hint" id="ovNote">Изменено в таблице: ${state.over.size} <button class="btn link small" type="button" id="resetOv">Сбросить правки таблицы</button></div>` : "";
  return `<div class="block" id="chars"><h2>Характеристики</h2>
    <table class="chars"><thead><tr><th>Характеристика</th><th>Из текста</th><th>Значение</th><th>Ед.</th><th>Источник</th><th></th></tr></thead>
    <tbody>${rows || `<tr><td colspan="6" class="muted">Характеристики КТРУ не найдены</td></tr>`}</tbody></table>${edited}</div>`;
}
function extrasBlock(issues) {
  const list = state.chars.map((c, i) => [c, i]).filter(([c]) => c.origin === "new");
  if (!list.length) return "";
  return `<div class="block extras" id="extras"><h2>Дополнения</h2>
    <div class="muted">Свойств нет ни в КТРУ, ни в выгрузках портала. Код по ним не сужается, перед публикацией их нужно проверить.</div>
    <table class="chars"><thead><tr><th>Свойство</th><th>Из текста</th><th>Значение</th><th>Ед.</th><th>Статус</th><th></th></tr></thead>
    <tbody>${list.map(([c, i]) => charRow(c, i, issues)).join("")}</tbody></table></div>`;
}
function correctionsBlock(data) {
  const list = correctionsList(data);
  if (!list.length) return "";
  return `<div class="block" id="corrBlock"><h2>Исправления</h2>${list.map((c, k) => `<div class="corr">
      <span class="kind">${esc(KINDS[c.kind] || c.kind || "исправление")}</span>
      ${c.field ? `<b>${esc(c.field)}:</b> ` : ""}<span class="from">${esc(c.from)}</span> → <span class="to">${esc(c.to)}</span>
      ${c.fixable ? `<button class="btn link small" type="button" data-fix="${k}">Исправить в тексте</button>` : ""}</div>`).join("")}</div>`;
}
function issuesBlock(issues) {
  const missing = issues.filter((x) => x.type === "missing" && x.field && !state.chars.some((c) => norm(c.name) === norm(x.field)));
  const other = issues.filter((x) => !(x.type === "missing" && x.field) && !x.message.startsWith("INPUT_CONFLICT"));
  const list = other.map((x, k) => `<div class="issue ${x.severity === "error" ? "error" : ""} ${esc(x.type)}">
      <div>${x.field ? `<b>${esc(x.field)}:</b> ` : ""}${esc(x.message)}</div>
      ${x.expected ? `<div class="exp">Ожидается: ${esc(x.expected)}</div>` : ""}
      ${x.suggestions.length ? `<div class="chips">${x.suggestions
        .map((s) => (x.field || x.span
          ? `<button class="chip" type="button" data-sug="${k}" data-val="${esc(s)}">${esc(s)}</button>`
          : `<span class="chip static">${esc(s)}</span>`)).join("")}</div>` : ""}
    </div>`).join("");
  const miss = missing.length
    ? `<div class="lbl">Не хватает обязательных характеристик:</div><div class="chips">${missing
      .map((x) => `<button class="chip add" type="button" data-miss="${esc(x.field)}">+ ${esc(x.field)}</button>`).join("")}</div>` : "";
  return { html: list + miss || `<div class="muted">Замечаний нет</div>`, other };
}
function funnelBlock(data, steps, search) {
  if (!steps.length && !search) return "";
  const checks = Array.isArray(data.checks) ? data.checks : [];
  const fails = checks.filter((c) => c.outcome === "FAIL");
  const unknown = new Set(checks.filter((c) => c.outcome === "UNKNOWN").map((c) => c.code)).size;
  let head = "";
  if (search && search.area) {
    const share = Math.max(0, Math.min(100, Math.round((100 * (search.compatible ?? 0)) / search.area)));
    head = `<div class="area-bar" title="Совместимы ${search.compatible} из ${search.area}"><div class="fill" style="width:${share}%"></div></div>
      <div class="muted">${search.full ? "Проверена вся область поиска" : "Область поиска проверена не полностью"}${unknown ? ` · без данных для проверки: ${unknown} (не отсеяны)` : ""}</div>`;
  }
  const rows = steps.map((s, k) => `<div class="step${k === steps.length - 1 ? " last" : ""}">
      <div class="step-head"><span>${esc(s.label)}</span><span class="num">${s.remaining}${s.removed ? ` <span class="minus">−${s.removed}</span>` : ""}</span></div>
      ${s.reason ? `<div class="reason">${esc(s.reason)}</div>` : ""}</div>`).join("");
  const shown = fails.slice(0, 5);
  const rest = fails.slice(5);
  const failRow = (c) => `<li><span class="code">${esc(c.code)}</span> <span class="muted">${esc(c.char_name)}</span><div class="reason">${esc(c.reason || "значение недопустимо")}</div></li>`;
  const failed = new Set(fails.map((c) => c.code)).size;
  const removed = search && search.area && search.compatible != null ? search.area - search.compatible : failed;
  const title = removed > failed ? `Отсеяно кодов: ${removed} (причины показаны для ${failed})` : `Отсеяно кодов: ${failed}`;
  const rejected = fails.length
    ? `<div class="lbl">${title}</div><ul class="rejected" id="rejected">${shown.map(failRow).join("")}</ul>${rest.length
      ? `<details><summary>Ещё ${rest.length}</summary><ul class="rejected">${rest.map(failRow).join("")}</ul></details>` : ""}` : "";
  const cands = Array.isArray(data.candidates) ? data.candidates : [];
  const candList = cands.length > 1
    ? `<div class="lbl">Подходящие коды</div><div class="cand-list">${cands.slice(0, 5).map((c) => `<div class="cand-item"><span class="code">${esc(c.code)}</span><span>${esc(c.name)}</span></div>`).join("")}</div>` : "";
  return `<div class="block" id="funnel"><h2>Подбор кода КТРУ</h2>${head}<div class="steps">${rows}</div>${rejected}${candList}</div>`;
}
function nextStepsBlock(data) {
  let items = Array.isArray(data.next_steps_detail) && data.next_steps_detail.length
    ? data.next_steps_detail.map((x) => (typeof x === "string" ? { text: x, required: true } : { text: x.text || "", required: x.required !== false }))
    : (data.next_steps || []).map((x) => ({ text: String(x), required: true }));
  if (!items.length) return "";
  items = [...items.filter((x) => x.required), ...items.filter((x) => !x.required)];
  return `<div class="block" id="next"><h2>Что сделать дальше</h2><ul class="next">${items
    .map((x) => `<li class="${x.required ? "req" : "opt"}">${esc(x.text)}${x.required ? "" : ' <span class="muted">(необязательно)</span>'}</li>`).join("")}</ul></div>`;
}

function statusLine(data, match, card) {
  const ms = data.debug && data.debug.elapsed_ms != null ? ` · ${Math.round(data.debug.elapsed_ms)} мс` : "";
  const q = data.question && data.question.field && (data.question.options || []).length ? data.question.field : "";
  let text = "Нужно уточнение";
  const cardHint = card === "INCOMPLETE" ? " · заполните карточку" : card === "HAS_UNVERIFIED_EXTRAS" ? " · проверьте дополнения" : "";
  if (match === "MATCHED") text = `Код КТРУ определён: ${data.best_ktru ? data.best_ktru.code : ""}${cardHint}`;
  else if (match === "INPUT_CONFLICT") text = "Подбор остановлен: в описании противоречивые значения";
  else if (match === "NO_MATCH_IN_SNAPSHOT") text = "Совместимых кодов КТРУ нет";
  else if (q) text = `Нужно уточнение: ${q}`;
  $("status").className = `status ${MATCH[match][1]}`;
  $("status").textContent = text + ms;
}

function marks() {
  const out = [];
  const d = state.data;
  for (const c of state.chars) {
    if (!c.span || c.span.end <= c.span.start) continue;
    out.push({ s: c.span.start, e: c.span.end, cls: c.origin === "new" ? "fact extra" : "fact", name: norm(c.name), title: `${c.name}: ${withUnit(c)}` });
    if (state.focus === norm(c.name)) out.push({ s: c.span.start, e: c.span.end, cls: "focus", name: norm(c.name), title: "" });
  }
  for (const raw of d.issues || []) {
    const i = normIssue(raw);
    if (i.type === "missing" || !i.span || i.span.end <= i.span.start) continue;
    out.push({ s: i.span.start, e: i.span.end, cls: i.severity === "error" ? "error" : "warning", name: "", title: i.message });
  }
  for (const a of d.ambiguities || []) {
    if (a.end > a.start) out.push({ s: a.start, e: a.end, cls: "warning", name: "", title: a.reason || "отдельный товар" });
  }
  return out;
}
function paint(text, list) {
  const cuts = new Set([0, text.length]);
  for (const m of list) { cuts.add(Math.max(0, Math.min(text.length, m.s))); cuts.add(Math.max(0, Math.min(text.length, m.e))); }
  const points = [...cuts].sort((a, b) => a - b);
  let html = "";
  for (let k = 0; k < points.length - 1; k++) {
    const a = points[k], b = points[k + 1];
    const piece = esc(text.slice(a, b));
    const on = list.filter((m) => m.s <= a && m.e >= b);
    if (!on.length) { html += piece; continue; }
    const cls = [...new Set(on.flatMap((m) => m.cls.split(" ")))].join(" ");
    const named = on.find((m) => m.cls === "focus") || on.find((m) => m.name);
    const title = [...new Set(on.map((m) => m.title).filter(Boolean))].join("; ");
    html += `<mark class="${cls}"${named ? ` data-name="${esc(named.name)}"` : ""} title="${esc(title)}">${piece}</mark>`;
  }
  return html;
}
function drawSource() {
  const d = state.data;
  if (!d) { $("source").hidden = true; return; }
  $("source").hidden = false;
  $("hl").innerHTML = paint(String(d.input_text ?? ""), marks());
  const box = $("focusLine");
  const c = state.focus ? state.chars.find((x) => norm(x.name) === state.focus) : null;
  if (!c) { box.hidden = true; box.innerHTML = ""; return; }
  const before = c.user_input || (c.span ? String(d.input_text).slice(c.span.start, c.span.end) : "");
  const after = withUnit(c);
  box.hidden = false;
  box.innerHTML = `<div class="focus-name">${esc(c.name)}${c.origin === "new" ? ' <span class="badge new">дополнение</span>' : ""}</div>
    <div class="was-now"><span class="was"><span class="cap">было</span>${before ? esc(before) : "в тексте нет"}</span>
    <span class="arrow">→</span><span class="now"><span class="cap">стало</span>${after ? esc(after) : "не заполнено"}</span></div>`;
}
function setFocus(name, scroll) {
  state.focus = name || null;
  document.querySelectorAll("#result tr[data-row]").forEach((tr) => tr.classList.toggle("active", tr.dataset.name === state.focus));
  drawSource();
  if (scroll) {
    const tr = document.querySelector(`#result tr[data-name="${CSS.escape(state.focus || "")}"]`);
    if (tr) tr.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

function draw() {
  const data = state.data;
  if (!data) return;
  const active = document.activeElement;
  const keep = active && active.dataset && active.dataset.i !== undefined
    ? { i: active.dataset.i, k: active.dataset.k, pos: active.selectionStart } : null;
  const issues = (data.issues || []).map(normIssue);
  const steps = normSteps(data);
  const search = searchOf(data, steps);
  const match = matchOf(data);
  const card = cardOf(data);
  statusLine(data, match, card);
  const ib = issuesBlock(issues);
  const product = data.product_guess ? ` · товар: <b>${esc(data.product_guess)}</b>` : "";
  $("result").className = "result";
  $("result").innerHTML = `
    ${badgesBlock(data, match, card, search, steps)}
    ${actionBlock(data, match)}
    ${bestBlock(data, match)}
    <div class="recognized muted">Категория: <b>${esc(DOMAINS[data.detected_domain] || "не определена")}</b>${product}</div>
    ${charsBlock(issues)}
    ${extrasBlock(issues)}
    ${correctionsBlock(data)}
    <div class="block" id="issues"><h2>Подсказки</h2>${ib.html}</div>
    ${funnelBlock(data, steps, search)}
    ${nextStepsBlock(data)}`;
  bind(ib.other, data);
  drawSource();
  if (keep) {
    const el = $("result").querySelector(`[data-i="${keep.i}"][data-k="${keep.k}"]`);
    if (el) { el.focus(); try { if (keep.pos != null) el.setSelectionRange(keep.pos, keep.pos); } catch (_) { } }
  }
}

function editRow(row, key, value) {
  const prev = String(row[key] ?? "");
  row[key] = value;
  if (key === "value" && syncText(row, prev, value)) return;
  if (!state.over.size) state.overText = $("text").value;
  state.over.set(norm(row.name), { name: row.name, value: String(row.value ?? ""), unit: row.unit || "" });
}
function syncText(row, prev, next) {
  if (!row.span || !prev || !next || !textMatchesData()) return false;
  const text = String(state.data.input_text);
  const frag = text.slice(row.span.start, row.span.end);
  const at = frag.toLowerCase().indexOf(prev.toLowerCase());
  if (at < 0) return false;
  const start = row.span.start + at;
  $("text").value = text.slice(0, start) + next + text.slice(start + prev.length);
  return true;
}
function removeRow(row) {
  if (state.over.delete(norm(row.name)) && !row.span) { analyze(); return; }
  if (row.span && cutSpans([row.span])) analyze();
}

function bind(other, data) {
  const root = $("result");
  root.querySelectorAll("tr[data-row]").forEach((tr) => {
    tr.addEventListener("click", () => setFocus(tr.dataset.name, false));
    tr.addEventListener("focusin", () => setFocus(tr.dataset.name, false));
  });
  root.querySelectorAll("[data-k]").forEach((el) => {
    el.addEventListener("change", () => {
      editRow(state.chars[+el.dataset.i], el.dataset.k, el.value);
      analyze();
    });
  });
  root.querySelectorAll("[data-del]").forEach((el) =>
    el.addEventListener("click", (e) => { e.stopPropagation(); removeRow(state.chars[+el.dataset.del]); }));
  root.querySelectorAll("[data-answer]").forEach((el) =>
    el.addEventListener("click", () => answer(data.question.field, data.question.options[+el.dataset.answer])));
  const groups = conflictGroups();
  root.querySelectorAll("[data-keep]").forEach((el) =>
    el.addEventListener("click", () => {
      const [g, j] = el.dataset.keep.split(":").map(Number);
      keepValue(groups[g], groups[g][j]);
    }));
  const fixes = correctionsList(data);
  root.querySelectorAll("[data-fix]").forEach((el) => el.addEventListener("click", () => applyFix(fixes[+el.dataset.fix])));
  const reset = $("resetOv");
  if (reset) reset.addEventListener("click", () => { dropOverrides(); analyze(); });
  root.querySelectorAll("[data-sug]").forEach((el) =>
    el.addEventListener("click", () => {
      const iss = other[+el.dataset.sug];
      const row = iss.field ? state.chars.find((c) => norm(c.name) === norm(iss.field)) : null;
      if (row) editRow(row, "value", el.dataset.val);
      else if (iss.field) {
        if (!state.over.size) state.overText = $("text").value;
        state.over.set(norm(iss.field), { name: iss.field, value: el.dataset.val, unit: "" });
      } else if (iss.span && textMatchesData()) {
        const text = String(state.data.input_text);
        $("text").value = text.slice(0, iss.span.start) + el.dataset.val + text.slice(iss.span.end);
      } else return;
      analyze();
    }));
  root.querySelectorAll("[data-miss]").forEach((el) =>
    el.addEventListener("click", () => {
      const name = el.dataset.miss;
      if (state.chars.some((c) => norm(c.name) === norm(name))) return;
      state.chars.push(normChar({ name, value: "", origin: "ktru", required: true }));
      draw();
      const v = root.querySelectorAll('[data-k="value"]');
      if (v.length) v[v.length - 1].focus();
    }));
}

async function loadDemos() {
  const res = await fetch("/api/demo-cases");
  const cases = await res.json();
  const box = $("demos");
  box.innerHTML = "";
  for (const c of cases) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = c.title;
    b.onclick = () => {
      dropOverrides();
      state.answer = null;
      $("text").value = c.text;
      $("domain").value = c.domain_hint || "";
      analyze();
    };
    box.appendChild(b);
  }
}

$("run").addEventListener("click", () => analyze());
$("undo").addEventListener("click", undo);
$("text").addEventListener("input", (e) => {
  const t = (e && e.inputType) || "";
  if (t === "insertFromPaste" || t === "insertFromDrop") dropOverrides();
  state.answer = null;
  schedule();
});
$("text").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); analyze(); }
});
$("domain").addEventListener("change", () => analyze());
$("hl").addEventListener("click", (e) => {
  const m = e.target.closest("mark[data-name]");
  if (m) setFocus(m.dataset.name, true);
});
$("clear").addEventListener("click", () => {
  clearTimeout(state.timer);
  state.seq++;
  $("text").value = "";
  $("domain").value = "";
  dropOverrides();
  Object.assign(state, { data: null, chars: [], history: [], done: null, restoring: null, focus: null, answer: null, prevSearch: null });
  refreshUndo();
  $("source").hidden = true;
  $("status").className = "status idle";
  $("status").textContent = "Введите описание товара";
  $("result").className = "result empty";
  $("result").textContent = "Здесь появится результат проверки";
});
loadDemos().catch(() => { $("demos").innerHTML = '<span class="muted">Примеры недоступны</span>'; });
