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
    render(data);
  } catch (e) {
    if (seq !== state.seq) return;
    $("status").className = "status error";
    $("status").textContent = "Ошибка";
    $("result").className = "result";
    $("result").innerHTML = `<div class="issue error">${escapeHtml(e.message)}</div>`;
  }
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
  const next = data.next_steps && data.next_steps.length
    ? `<div class="block"><h2>Что сделать дальше</h2><ul class="next">${data.next_steps.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>`
    : "";
  const elapsed = data.debug && data.debug.elapsed_ms != null ? `<span class="muted"> · ${data.debug.elapsed_ms} мс</span>` : "";

  $("result").className = "result";
  $("result").innerHTML = `
    <div class="block"><h2>Распознано${elapsed}</h2>
      <div class="muted">Категория: <b>${escapeHtml(data.detected_domain || "—")}</b> · Товар: <b>${escapeHtml(data.product_guess || "—")}</b></div></div>
    ${best}
    <div class="block"><h2>Характеристики</h2>${charsTable(issues)}${state.dirty.size ? `<div class="hint" id="ovNote">Изменено в таблице: ${state.dirty.size}${state.textNote ? " · правки таблицы имеют приоритет над текстом" : ""} <button class="btn ghost small" id="resetOv">Сбросить правки таблицы</button></div>` : ""}</div>
    <div class="block"><h2>Подсказки</h2>${ib.html}</div>
    <div class="block"><h2>Сужение кодов КТРУ</h2>${funnelBlock(steps, candidates)}</div>
    ${next}`;
  bind(ib.other);

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
  schedule(false);
});
$("domain").addEventListener("change", () => schedule(false));
$("clear").onclick = () => {
  clearTimeout(state.timer); state.seq++;
  $("text").value = ""; $("domain").value = "";
  state.data = null; state.chars = []; resetOverrides(); state.lastKey = null;
  $("status").className = "status idle"; $("status").textContent = "Введите описание товара";
  $("result").className = "result empty"; $("result").textContent = "Здесь появится результат проверки";
};
loadDemos().catch(console.error);
