/* Refill of family "corporate_business_overview" (KISE Business) — same grid, helpers and geometry,
   rethemed to Moscow Supplier Portal colours. Builds deck A (7 slides) and deck B (10 slides). */
const path = require('path');
const fs = require('fs');
const PptxGenJS = require('pptxgenjs');
const DOCS = path.join(__dirname, '..');
const SRC = fs.existsSync(path.join(DOCS, 'src', 'process.png')) ? path.join(DOCS, 'src') : DOCS;
const M = require('./metrics.js');

let BLUE = '264B82';     // dark portal blue
let BRIGHT = '1E88E5';   // bright accent blue
let LIGHTB = '5AA9F0';   // thin rules
let PALE = 'EAF2FC';
let GRAYBG = 'F1F3F6';
let WHITE = 'FFFFFF';
let INK = '1F2A3C';
let GRAY = '4A5568';
let MUTED = '718096';
let FONT = 'Inter';

const TEXT_BASE = { margin: 0, valign: 'top', isTextBox: true };
function text(s, c, b, o) { s.addText(c, Object.assign({ x: b[0], y: b[1], w: b[2], h: b[3] }, TEXT_BASE, o)); }
function body(s, c, b, o) { text(s, c, b, Object.assign({ fontFace: FONT, fontSize: 14, color: GRAY, lineSpacingMultiple: 1.15 }, o)); }
function heading(s, c, b, o) { text(s, c, b, Object.assign({ fontFace: FONT, fontSize: 16, bold: true, color: INK, lineSpacingMultiple: 1.1 }, o)); }
function headline(s, c, b, o) { text(s, c, b, Object.assign({ fontFace: FONT, fontSize: 32, bold: true, color: BLUE, lineSpacingMultiple: 0.95 }, o)); }
function roundRect(s, b, fill, o) {
  o = o || {}; const adj = o.adj === undefined ? 0.16667 : o.adj;
  s.addShape('roundRect', Object.assign({ x: b[0], y: b[1], w: b[2], h: b[3], rectRadius: adj * Math.min(b[2], b[3]),
    fill: fill ? { color: fill } : { type: 'none' }, line: o.line || { type: 'none' } }, o.rotate ? { rotate: o.rotate } : {}));
}
function rect(s, b, fill) { s.addShape('rect', { x: b[0], y: b[1], w: b[2], h: b[3], fill: { color: fill }, line: { type: 'none' } }); }
function hLine(s, x, y, w, c, wd) { s.addShape('line', { x: x, y: y, w: w, h: 0, line: { color: c, width: wd } }); }
function vLine(s, x, y, h, c, wd) { s.addShape('line', { x: x, y: y, w: 0, h: h, line: { color: c, width: wd } }); }
function bullets(s, items, b, o) {
  body(s, items.map(function (t, i) { return { text: t, options: { breakLine: i < items.length - 1, bullet: { indent: 16 }, paraSpaceBefore: 6 } }; }), b, o);
}

let PAGE_BG = null;
function chrome(s, n, total, o) {
  o = o || {};
  if (PAGE_BG) s.background = { color: PAGE_BG };
  [[0, 0], [0.0624, 0.0624], [0.1249, 0], [0, 0.1249], [0.1249, 0.1249]].forEach(function (d) { rect(s, [0.3581 + d[0], 0.303 + d[1], 0.0624, 0.0624], BLUE); });
  text(s, 'Tender Hack 2026', [0.6116, 0.29, 2.6, 0.22], { fontFace: FONT, fontSize: 13, bold: true, color: BLUE });
  text(s, 'Помощник заполнения характеристик СТЕ', [7.3, 0.29, 5.675, 0.22], { fontFace: FONT, fontSize: 11, color: MUTED, align: 'right' });
  if (o.railL !== false) vLine(s, 0.3581, 1.7891, 4.0717, BLUE, 2);
  if (o.railR !== false) vLine(s, 12.9752, 1.7891, 4.0717, BLUE, 2);
  hLine(s, 5.4114, 7.1034, 0.9306, BLUE, 1);
  s.addShape('ellipse', { x: 6.5859, y: 7.0226, w: 0.1615, h: 0.1615, fill: { type: 'none' }, line: { color: BLUE, width: 1 } });
  const pad = function (k) { return (k < 10 ? '0' : '') + k; };
  text(s, pad(n) + ' / ' + pad(total), [10.9306, 6.99, 2.0447, 0.229], { fontFace: FONT, fontSize: 10, bold: true, color: BLUE, align: 'right' });
}

/* ---------------------------------------------------------------- slides */
function sCover(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t, { railR: false });
  headline(s, 'Помощник\nзаполнения\nхарактеристик СТЕ', [1.2383, 1.45, 6.2, 2.4], { fontSize: 44, lineSpacingMultiple: 0.95 });
  headline(s, '01', [1.2383, 4.25, 0.75, 0.5], { fontSize: 34, color: BRIGHT });
  body(s, 'Поставщик описывает товар свободным текстом, а для СТЕ нужны характеристики по КТРУ — подобрать группу и заполнить обязательные поля сложно.',
    [2.05, 4.25, 4.6, 1.15], { fontSize: 15 });
  body(s, 'Итог: карточки отклоняются, позиции дублируются, сравнивать цены тяжело.', [1.2383, 5.6, 5.4, 0.6], { fontSize: 14, bold: true, color: INK });
  roundRect(s, [7.55, 1.55, 4.95, 4.75], GRAYBG, { adj: 0.08 });
  text(s, 'Типичные ошибки в карточке', [7.85, 1.78, 4.4, 0.3], { fontFace: FONT, fontSize: 13, bold: true, color: BLUE });
  const cards = [['Опечатки', 'в названиях и значениях'], ['Единицы', 'неверные или несовместимые'],
    ['Вне списка', 'значения не из допустимых КТРУ'], ['Пропуски', 'обязательных характеристик']];
  cards.forEach(function (c, i) {
    const x = 7.85 + (i % 2) * 2.25, y = 2.3 + Math.floor(i / 2) * 1.92;
    roundRect(s, [x, y, 2.1, 1.72], WHITE, { adj: 0.1 });
    headline(s, c[0], [x + 0.15, y + 0.35, 1.8, 0.4], { fontSize: 19, color: BRIGHT, align: 'center' });
    body(s, c[1], [x + 0.15, y + 0.85, 1.8, 0.65], { fontSize: 12, align: 'center' });
  });
  return s;
}

function sKtru(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Код КТРУ — это группа товаров, а не один товар', [1.0, 1.2, 11.3, 0.6]);
  body(s, 'Одну СТЕ предлагают многие поставщики, каждый по своей цене — из этих цен считается референтная.', [1.0, 1.9, 11.0, 0.4], { fontSize: 15 });
  const steps = [
    ['01', 'Код КТРУ', 'Группа однородных товаров со своим списком обязательных характеристик'],
    ['02', 'СТЕ', 'Позиция внутри группы с заполненными значениями характеристик'],
    ['03', 'Цены поставщиков', 'На одну СТЕ свои цены ставят многие поставщики'],
    ['04', 'Референтная цена', 'Рассчитывается из цен многих поставщиков на одну СТЕ']];
  steps.forEach(function (st, i) {
    const x = 1.0 + i * 2.93, y = 2.75, last = i === 3;
    roundRect(s, [x, y, 2.5, 2.85], last ? BLUE : GRAYBG, { adj: 0.1 });
    headline(s, st[0], [x + 0.25, y + 0.25, 1.0, 0.5], { fontSize: 28, color: last ? WHITE : BRIGHT });
    heading(s, st[1], [x + 0.25, y + 0.85, 2.1, 0.6], { color: last ? WHITE : INK });
    body(s, st[2], [x + 0.25, y + 1.55, 2.05, 1.15], { fontSize: 12.5, color: last ? 'DCE6F5' : GRAY });
    if (i < 3) text(s, '→', [x + 2.5, y + 0.95, 0.43, 0.5], { fontFace: FONT, fontSize: 26, bold: true, color: BRIGHT, align: 'center' });
  });
  hLine(s, 1.0, 5.85, 11.3, LIGHTB, 1);
  body(s, 'Поэтому важно не плодить дубли СТЕ: правильная привязка к карточке объединяет предложения и делает референтную цену точнее.',
    [1.0, 6.0, 11.3, 0.7], { fontSize: 14, bold: true, color: INK });
  return s;
}

function sSolution(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Из свободного текста — в проверенную таблицу', [1.3, 1.45, 4.4, 1.4], { fontSize: 28 });
  body(s, 'Пользователь вводит описание — сервис выделяет характеристики и сразу показывает их в редактируемой таблице.', [1.3, 3.0, 4.2, 1.1], { fontSize: 15 });
  roundRect(s, [1.3, 4.35, 4.2, 1.25], GRAYBG, { adj: 0.12 });
  text(s, 'Пример ввода', [1.5, 4.5, 3.8, 0.25], { fontFace: FONT, fontSize: 11, bold: true, color: BRIGHT });
  body(s, '«Стол письменный 1200 на 700 на 750 миллиметров»', [1.5, 4.8, 3.8, 0.7], { fontSize: 13, italic: true, color: INK });
  const rows = [
    ['01', 'Бейдж источника', 'У каждой характеристики: КТРУ, Портал или Новая.'],
    ['02', 'Подсказки', 'Что не так и что ожидается; исправление в один клик, недостающие обязательные — кнопкой.'],
    ['03', 'Воронка сужения', 'Сколько кодов КТРУ осталось после каждого шага и почему.'],
    ['04', 'Автопересчёт', 'Любая правка пересчитывает результат (≈600 мс задержки ввода).']];
  rows.forEach(function (r, i) {
    const y = 1.45 + i * 1.22;
    hLine(s, 6.17, y, 5.6, LIGHTB, 1);
    headline(s, r[0], [6.15, y + 0.2, 0.8, 0.5], { fontSize: 30, color: BRIGHT });
    heading(s, r[1], [6.95, y + 0.15, 4.8, 0.3]);
    body(s, r[2], [6.95, y + 0.5, 4.8, 0.62], { fontSize: 13 });
  });
  hLine(s, 6.17, 1.45 + 4 * 1.22, 5.6, LIGHTB, 1);
  return s;
}

function sUI(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Интерфейс: всё на одном экране', [1.0, 1.15, 11.3, 0.6]);
  const cards = [
    { big: 'Бейджи', label: 'Источник характеристики', items: ['КТРУ — есть в спецификации кода, вкл. незаполненные обязательные', 'Портал — совпало с характеристиками портала', 'Новая — не найдена, идёт на модерацию'], badges: true },
    { big: '≈600 мс', label: 'Редактируемая таблица', items: ['Любое значение правится прямо в таблице', 'После правки всё пересчитывается заново'] },
    { big: '355 → 2', label: 'Воронка сужения', items: ['Домен → наименование → ОКПД2 → характеристики', 'На каждом шаге: сколько кодов осталось и почему'], hi: true },
    { big: '27 м → 27 мм', label: 'Подсказки', items: ['Что не так и что ожидается', 'До трёх вариантов исправления в один клик'] }];
  cards.forEach(function (c, i) {
    const x = 1.0 + i * 2.88, y = c.hi ? 1.95 : 2.1, h = c.hi ? 4.6 : 4.3, col = c.hi ? BRIGHT : BLUE;
    roundRect(s, [x, y, 2.6, h], null, { adj: 0.08, line: { color: col, width: c.hi ? 2.25 : 1.5 } });
    headline(s, c.big, [x + 0.15, y + 0.3, 2.3, 0.5], { fontSize: c.big.length > 9 ? 20 : 24, color: col, align: 'center' });
    heading(s, c.label, [x + 0.15, y + 0.9, 2.3, 0.55], { fontSize: 14, align: 'center' });
    bullets(s, c.items, [x + 0.2, y + 1.55, 2.25, 2.1], { fontSize: 12 });
    if (c.badges) {
      [['КТРУ', BLUE], ['Портал', BRIGHT], ['Новая', 'E8A33D']].forEach(function (b, k) {
        roundRect(s, [x + 0.15 + k * 0.78, y + h - 0.6, 0.72, 0.3], b[1], { adj: 0.5 });
        text(s, b[0], [x + 0.15 + k * 0.78, y + h - 0.6, 0.72, 0.3], { fontFace: FONT, fontSize: 10, bold: true, color: WHITE, align: 'center', valign: 'middle' });
      });
    }
  });
  return s;
}

function sBpmn(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Процесс: «правка → пересчёт» до подтверждения', [1.0, 1.15, 11.3, 0.6], { fontSize: 28 });
  roundRect(s, [0.85, 1.95, 11.65, 4.35], GRAYBG, { adj: 0.05 });
  const w = 11.25, h = w * 630 / 1720;
  s.addImage({ path: path.join(SRC, 'process.png'), x: 1.05, y: 1.95 + (4.35 - h) / 2, w: w, h: h });
  body(s, 'Дорожки: Пользователь / Сервис / Данные. Исходник: docs/process.bpmn (Camunda Modeler / bpmn.io).', [1.0, 6.45, 11.3, 0.3], { fontSize: 12, color: MUTED });
  return s;
}

function sComponents(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Архитектура: конвейер модулей и заранее собранный индекс', [1.0, 1.4, 3.5, 2.0], { fontSize: 26 });
  bullets(s, ['Веб-интерфейс (HTML/JS) → FastAPI → parser → unifier → matcher → engine',
    'SQLite-индекс собирается заранее скриптом build_index.py из XML КТРУ и выгрузки XLSX портала',
    'Запрос обслуживается локально, без внешних сервисов'], [1.0, 3.55, 3.45, 2.8], { fontSize: 13 });
  roundRect(s, [4.7, 1.6, 7.95, 4.5], GRAYBG, { adj: 0.05 });
  const w = 7.65, h = w * 640 / 1300;
  s.addImage({ path: path.join(SRC, 'components.png'), x: 4.85, y: 1.6 + (4.5 - h) / 2, w: w, h: h });
  return s;
}

function sTech(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Технологии: почему без LLM', [1.5, 1.2, 10.3, 0.6], { align: 'center' });
  const q = [
    ['Py', 'Python + FastAPI', 'Быстрая разработка, контракт через Pydantic, автодокументация API', BRIGHT],
    ['DB', 'SQLite', 'Один файл без отдельного сервера, быстрый поиск по справочнику, легко в Docker', BRIGHT],
    ['≠AI', 'Правила, не LLM', 'Детерминированно и объяснимо: у каждого сужения есть причина. Офлайн, без утечки данных', BLUE],
    ['JS', 'Чистый HTML/JS', 'Нет сборки, легко встроить в портал, стиль Портала поставщиков', BRIGHT]];
  q.forEach(function (c, i) {
    const x = 1.25 + i * 2.85;
    s.addShape('round2DiagRect', { x: x, y: 2.45, w: 2.6, h: 3.0, flipH: true, fill: { color: c[3] }, line: { type: 'none' } });
    s.addShape('ellipse', { x: x - 0.2, y: 2.22, w: 0.8, h: 0.8, fill: { color: WHITE }, line: { color: c[3], width: 1.5 } });
    text(s, c[0], [x - 0.2, 2.22, 0.8, 0.8], { fontFace: FONT, fontSize: c[0].length > 2 ? 15 : 18, bold: true, color: c[3], align: 'center', valign: 'middle' });
    heading(s, c[1], [x + 0.25, 3.2, 2.15, 0.35], { color: WHITE });
    body(s, c[2], [x + 0.25, 3.62, 2.15, 1.75], { fontSize: 12.5, color: WHITE });
  });
  body(s, 'ТЗ запрещает облачные LLM API; локальная модель допустима (до 40 ГБ VRAM), но задача сводится к сопоставлению с закрытым справочником — правила дают объяснимый результат и ничего не выдумывают.',
    [1.25, 5.8, 11.0, 0.8], { fontSize: 13, color: INK });
  return s;
}

function sResults(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Код в топ-3: ' + M.main.top3Pct + ' на основном наборе, ' + M.heldOut.top3Pct + ' на отложенном', [1.0, 1.2, 11.5, 0.5], { fontSize: 24 });
  roundRect(s, [1.0, 1.9, 5.3, 0.36], PALE, { adj: 0.5 });
  text(s, M.versionNote, [1.0, 1.9, 5.3, 0.36], { fontFace: FONT, fontSize: 11.5, bold: true, color: BLUE, align: 'center', valign: 'middle' });
  roundRect(s, [1.0, 2.5, 5.3, 4.1], GRAYBG, { adj: 0.07 });
  text(s, 'Основной набор · ' + M.main.cases + ' кейсов', [1.2, 2.62, 4.9, 0.25], { fontFace: FONT, fontSize: 11, bold: true, color: BLUE });
  text(s, 'Отложенный набор · ' + M.heldOut.cases + ' новых, код не подстраивался', [1.2, 4.3, 4.9, 0.25], { fontFace: FONT, fontSize: 11, bold: true, color: BLUE });
  [[M.main.top1Pct, 'код 1-й', M.main.top1], [M.main.top3Pct, 'код в топ-3', M.main.top3], [M.main.statusPct, 'статус', M.main.status],
   [M.heldOut.top1Pct, 'код 1-й', M.heldOut.top1], [M.heldOut.top3Pct, 'код в топ-3', M.heldOut.top3], [M.heldOutStatusPct, 'статус', M.heldOutStatus]].forEach(function (c, i) {
    const x = 1.2 + (i % 3) * 1.65, y = 2.92 + Math.floor(i / 3) * 1.66;
    roundRect(s, [x, y, 1.55, 1.25], WHITE, { adj: 0.1 });
    headline(s, c[0], [x + 0.05, y + 0.13, 1.45, 0.45], { fontSize: 26, color: BRIGHT, align: 'center' });
    body(s, c[1] + '\n' + c[2], [x + 0.05, y + 0.64, 1.45, 0.55], { fontSize: 11.5, align: 'center', lineSpacingMultiple: 1.05 });
  });
  body(s, [{ text: 'Код первым по категориям:', options: { bold: true, color: INK, breakLine: true } }, { text: 'мебель ' + M.heldOutByDomain.furniture + ' · инструменты ' + M.heldOutByDomain.tools + ' · одежда ' + M.heldOutByDomain.clothing }], [1.2, 5.92, 4.9, 0.55], { fontSize: 11.5 });
  const hd = { bold: true, color: WHITE, fill: { color: BLUE } };
  const v = function (x) { return { text: x, options: { align: 'right', bold: true, color: BLUE } }; };
  const d = M.heldOutByDomain, ie = M.injectedErrors;
  const rows = [
    [{ text: 'Метрика', options: hd }, { text: 'Значение', options: Object.assign({ align: 'right' }, hd) }],
    ['Внесённые ошибки пойманы**', v(ie.caught)],
    ['Время ответа: медиана / p95*', v(M.latencyMedian + ' / ' + M.latencyP95)],
    ['Нагрузка: параллельных запросов', v(M.loadParallel + ' без ошибок')],
    ['Справочник КТРУ (весь архив)', v(M.ktruItems + ' позиция')],
    ['Автотесты pytest', v(M.autotests)],
    ['Чистая сборка индекса', v(M.indexBuild)]];
  s.addTable(rows, { x: 6.75, y: 2.5, w: 5.75, colW: [3.25, 2.5], rowH: 0.33, fontFace: FONT, fontSize: 12, color: INK, border: { type: 'solid', pt: 0.75, color: 'D5DCE6' }, valign: 'middle', margin: 0.06 });
  body(s, M.falseAlarmsSlide, [6.75, 4.85, 5.75, 0.3], { fontSize: 12, bold: true, color: INK });
  body(s, '* замер eval-скрипта qa/run_eval.py\n** единицы ' + ie.units + ', числа ' + ie.unrealistic + ', несуществующие ' + ie.nonExistent + ', опечатки ' + ie.typos + '; ' + M.injectedCaveat,
    [6.75, 5.3, 5.75, 0.55], { fontSize: 10.5, color: MUTED });
  body(s, [{ text: 'Демо: ', options: { bold: true, color: INK } }, { text: 'мебель, одежда, инструменты; ' + M.funnelOutput + '.' }], [6.75, 6.0, 5.75, 0.55], { fontSize: 12 });
  return s;
}

function sRoadmap(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t, { railR: false });
  headline(s, 'Ограничения и план развития', [1.3, 1.3, 4.2, 1.2]);
  bullets(s, ['Три домена: мебель, одежда, инструменты',
    'Итог воронки — ' + M.funnelOutput.replace('на выходе ', '') + '; система говорит, что уточнить'], [5.75, 1.3, 6.6, 1.0], { fontSize: 13 });
  roundRect(s, [5.75, 2.5, 6.6, 0.85], 'FFF4D6', { adj: 0.12 });
  body(s, [{ text: 'Слабое место: ', options: { bold: true, color: INK } },
    { text: M.weakSpot }],
    [5.95, 2.6, 6.25, 0.7], { fontSize: 12.5 });
  text(s, 'План', [1.3, 3.55, 1.2, 0.35], { fontFace: FONT, fontSize: 18, bold: true, color: INK });
  const step = 2.65, x0 = 1.3;
  const st = [['01', 'Несуществующие значения', 'Ловить значения, которых нет в справочнике', 2.45, 0, true],
    ['02', 'Postgres', 'pg_trgm и GIN-индексы для нечёткого поиска по всему каталогу', 2.45, 0.15],
    ['03', 'Обновление КТРУ', 'Пересборка индекса по расписанию с атомарной подменой', 1.6, 0.3],
    ['04', 'Новые домены', 'Расширение словарями и данными — без смены архитектуры', 2.45, 0]];
  for (let i = 0; i < 5; i++) vLine(s, x0 + i * step, 4.0, 0.38, BRIGHT, 1);
  st.forEach(function (c, i) {
    const x = x0 + i * step, done = c[5];
    text(s, c[0], [x + 0.08, 4.1, 0.4, 0.2], { fontFace: FONT, fontSize: 10, bold: true, color: INK });
    if (done) {
      roundRect(s, [x + 0.55, 4.05, 1.25, 0.27], '2E8B57', { adj: 0.5 });
      text(s, '✓ сделано', [x + 0.55, 4.05, 1.25, 0.27], { fontFace: FONT, fontSize: 10.5, bold: true, color: WHITE, align: 'center', valign: 'middle' });
    }
    roundRect(s, [x, 4.55 + c[4], c[3], 0.19], done ? '2E8B57' : BRIGHT, { adj: 0.5 });
    heading(s, c[1], [x, 4.9 + c[4], 2.45, 0.5], { fontSize: 14 });
    body(s, c[2], [x, 5.48 + c[4], 2.35, 0.9], { fontSize: 12 });
  });
  return s;
}

function sTeam(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Команда и роли', [1.3, 1.3, 5.0, 0.6]);
  body(s, PAGE_BG ? 'Дальше — живое демо: чистый кейс, ошибка, неполное описание и пакет CSV.' : 'Процесс с дорожками — на BPMN; приёмка изменений — через PR.', [7.0, 1.4, 5.0, 0.5], { fontSize: 13, color: MUTED });
  const roles = [['Координация и интеграция', 'Приёмка и интеграция через PR'], ['Ядро КТРУ', 'Разбор, унификация, сужение кодов'],
    ['Интерфейс и защита', 'UI в стиле портала, BPMN, документация, презентация'], ['Тестирование и качество', 'Тест-кейсы и метрики QA']];
  roles.forEach(function (r, i) {
    const x = 1.75 + (i % 2) * 5.4, y = 2.55 + Math.floor(i / 2) * 1.85;
    roundRect(s, [x, y, 4.85, 1.55], GRAYBG, { adj: 0.12 });
    s.addShape('ellipse', { x: x - 0.42, y: y + 0.35, w: 0.85, h: 0.85, fill: { color: WHITE }, line: { color: BLUE, width: 1.5 } });
    text(s, '0' + (i + 1), [x - 0.42, y + 0.35, 0.85, 0.85], { fontFace: FONT, fontSize: 16, bold: true, color: BLUE, align: 'center', valign: 'middle' });
    heading(s, '[Имя] — [роль]', [x + 0.65, y + 0.2, 4.0, 0.35], { fontSize: 17 });
    body(s, r[0], [x + 0.65, y + 0.62, 4.0, 0.3], { fontSize: 13, bold: true, color: BRIGHT });
    body(s, r[1], [x + 0.65, y + 0.98, 4.0, 0.45], { fontSize: 12 });
  });
  return s;
}

/* ------------------------------------------------ final pre-defense deck (Figma UI-kit tokens) */
const F = M.final;
function setFinalTheme() {
  BLUE = '264B82'; BRIGHT = 'DB2B21'; LIGHTB = 'C5D3E6'; PALE = 'F9E3E1'; GRAYBG = 'FFFFFF'; WHITE = 'FFFFFF';
  INK = '1A1A1A'; GRAY = '1A1A1A'; MUTED = '5B6676'; PAGE_BG = 'E7EEF7';
  FONT = fs.existsSync('/usr/share/fonts') && require('child_process').execSync('fc-list : family').toString().indexOf('Open Sans') >= 0 ? 'Open Sans' : 'Inter';
}
const BADGE = { ktru: '264B82', portal: '1F8A8A', fresh: 'F07D1A' };
function pngSize(f) { const h = fs.readFileSync(f).subarray(16, 24); return { w: h.readUInt32BE(0), h: h.readUInt32BE(4) }; }
function pill(s, label, b, fill, o) {
  roundRect(s, b, fill, { adj: 0.5 });
  text(s, label, b, Object.assign({ fontFace: FONT, fontSize: 11, bold: true, color: WHITE, align: 'center', valign: 'middle' }, o));
}
function card(s, b) { roundRect(s, b, WHITE, { adj: 0.04, line: { color: 'D3DDEB', width: 0.75 } }); }
function label(s, t, b, o) { text(s, t, b, Object.assign({ fontFace: FONT, fontSize: 13, bold: true, color: BLUE }, o)); }

function fCover(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t, { railR: false });
  headline(s, 'Помощник\nзаполнения\nхарактеристик СТЕ', [1.24, 1.3, 6.1, 2.4], { fontSize: 38 });
  text(s, 'Свободный текст → код КТРУ → проверенная карточка', [1.24, 3.75, 6.0, 0.7], { fontFace: FONT, fontSize: 16, bold: true, color: BRIGHT });
  body(s, 'Поставщик описывает товар одной строкой, а для СТЕ нужен код КТРУ и обязательные характеристики. Код КТРУ — это группа товаров: подобрать её и заполнить поля вручную сложно.',
    [1.24, 4.55, 5.7, 1.15], { fontSize: 14 });
  body(s, 'Итог: карточки отклоняются, позиции дублируются, цены сложно сравнивать.', [1.24, 5.8, 5.7, 0.6], { fontSize: 13.5, bold: true });
  card(s, [7.55, 1.45, 4.95, 4.95]);
  label(s, 'Типичные ошибки в карточке', [7.85, 1.7, 4.4, 0.3]);
  [['Опечатки', 'в названиях и значениях'], ['Единицы', 'неверные или несовместимые'],
   ['Вне списка', 'значения не из допустимых КТРУ'], ['Пропуски', 'обязательных характеристик']].forEach(function (c, i) {
    const x = 7.85 + (i % 2) * 2.25, y = 2.2 + Math.floor(i / 2) * 2.0;
    roundRect(s, [x, y, 2.1, 1.8], PAGE_BG, { adj: 0.08 });
    headline(s, c[0], [x + 0.1, y + 0.38, 1.9, 0.4], { fontSize: 19, color: BRIGHT, align: 'center' });
    body(s, c[1], [x + 0.12, y + 0.9, 1.86, 0.7], { fontSize: 12.5, align: 'center' });
  });
  return s;
}

function fHow(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Как работает: текст → код КТРУ → проверенная карточка', [0.85, 1.0, 11.6, 0.6], { fontSize: 26 });
  const steps = [
    ['01', 'Ввод', '«Ключ гаечный 170х190 мм длина 27 м» — и кнопка «Проверить»'],
    ['02', 'Код КТРУ', 'Воронка ' + F.howFunnel + ': домен, наименование, ОКПД2, характеристики — с причиной на каждом шаге'],
    ['03', 'Карточка', 'Таблица с бейджами источника, подсказки и «было → стало»: «27 м» подсвечено, варианты 27 мм / 27 см']];
  steps.forEach(function (st, i) {
    const y = 1.9 + i * 1.62;
    card(s, [0.85, y, 4.95, 1.45]);
    headline(s, st[0], [1.05, y + 0.2, 0.75, 0.5], { fontSize: 28, color: BRIGHT });
    heading(s, st[1], [1.85, y + 0.2, 3.8, 0.3], { color: BLUE });
    body(s, st[2], [1.85, y + 0.55, 3.8, 0.85], { fontSize: 12.5 });
  });
  card(s, [6.05, 1.9, 6.43, 4.69]);
  // two crops of the retaken screenshot (px coords of docs/screens/main_result.png, 1425 px wide):
  // top = input with «27 м» highlight + result card; bottom = right column «Сужение кодов КТРУ» (1309 → 3)
  const mr = path.join(SRC, 'screens', 'main_result.png'), ms = pngSize(mr), iw = 6.23;
  const k1 = iw / ms.w, topH = 2.58;
  s.addImage({ path: mr, x: 6.15, y: 2.0, w: ms.w * k1, h: ms.h * k1, sizing: { type: 'crop', x: 0, y: 0, w: iw, h: topH } });
  hLine(s, 6.15, 4.65, iw, LIGHTB, 1);
  const fx = 520, fy = 1775, fwPx = 820, k2 = iw / fwPx, botH = 1.8;
  s.addImage({ path: mr, x: 6.15, y: 4.72, w: ms.w * k2, h: ms.h * k2, sizing: { type: 'crop', x: fx * k2, y: fy * k2, w: iw, h: botH } });
  return s;
}

function fDiff(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Чем мы отличаемся', [0.85, 1.0, 11.6, 0.6]);
  body(s, 'Пять свойств, которые видны в каждом ответе сервиса', [0.85, 1.62, 11.6, 0.35], { fontSize: 15, color: MUTED });
  const c = [
    ['Без нейросетей', 'Правила и справочник КТРУ: детерминированно, ничего не выдумывает'],
    ['Полностью офлайн', 'SQLite-индекс и FastAPI на одной машине — без интернета и внешних API'],
    ['Медиана < 0,1 с', 'Медиана ' + F.p50Range + ' на запрос; пакет из ' + F.batch.rows + ' строк — ' + F.batch.time],
    ['Объяснимость', 'Бейдж источника у каждой характеристики, причина на каждом шаге воронки, подсказки «было → стало»'],
    ['КТРУ → портал → NEW', 'Сначала спецификация кода КТРУ, затем характеристики портала; новая — только на модерацию']];
  c.forEach(function (d, i) {
    const x = 0.85 + i * 2.36, y = 2.25, w = 2.17, h = 3.65;
    card(s, [x, y, w, h]);
    rect(s, [x + 0.2, y + 0.25, 0.5, 0.06], BRIGHT);
    headline(s, '0' + (i + 1), [x + 0.2, y + 0.45, 1.0, 0.55], { fontSize: 30, color: BRIGHT });
    heading(s, d[0], [x + 0.2, y + 1.15, w - 0.35, 0.65], { fontSize: 15, color: BLUE });
    body(s, d[1], [x + 0.2, y + 1.85, w - 0.32, 1.7], { fontSize: 12 });
  });
  roundRect(s, [0.85, 6.12, 11.63, 0.52], BLUE, { adj: 0.3 });
  text(s, 'ТЗ запрещает облачные LLM API — а нашей задаче они и не нужны: это сопоставление с закрытым справочником.', [1.05, 6.12, 11.23, 0.52],
    { fontFace: FONT, fontSize: 13, bold: true, color: WHITE, valign: 'middle', align: 'center' });
  return s;
}

function fArch(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Процесс и архитектура: один локальный конвейер', [0.85, 1.0, 11.6, 0.6], { fontSize: 26 });
  const cols = [
    { x: 0.85, title: 'Процесс (BPMN): «правка → пересчёт» до подтверждения', img: 'process.png', ar: 630 / 1720,
      items: ['Дорожки: Пользователь / Сервис / Данные', 'Исходник docs/process.bpmn — Camunda Modeler, bpmn.io'] },
    { x: 6.78, title: 'Компоненты: parser → unifier → matcher → engine', img: 'components.png', ar: 640 / 1300,
      items: ['SQLite-индекс собирается заранее из XML КТРУ и XLSX портала', 'POST /api/analyze — ответ без внешних сервисов'] }];
  cols.forEach(function (c) {
    card(s, [c.x, 1.85, 5.7, 4.75]);
    label(s, c.title, [c.x + 0.2, 2.0, 5.3, 0.3]);
    const w = 5.3, h = w * c.ar, top = 2.45, area = 2.75;
    s.addImage({ path: path.join(SRC, c.img), x: c.x + 0.2, y: top + (area - h) / 2, w: w, h: h });
    body(s, c.items.map(function (t) { return '•  ' + t; }).join('\n'), [c.x + 0.2, 5.4, 5.3, 1.0], { fontSize: 12.5, paraSpaceBefore: 4 });
  });
  return s;
}

function fFill(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Дописать в один клик — и проверить пачкой из CSV', [0.85, 1.0, 11.6, 0.6], { fontSize: 26 });
  card(s, [0.85, 1.85, 5.75, 1.5]);
  label(s, 'Приоритет источников характеристик', [1.05, 1.97, 5.3, 0.3]);
  [['КТРУ', BADGE.ktru, 'спецификация кода'], ['Портал', BADGE.portal, 'карточки портала'], ['Новая', BADGE.fresh, 'на модерацию']].forEach(function (b, i) {
    const x = 1.05 + i * 1.85;
    pill(s, b[0], [x, 2.42, 1.35, 0.34], b[1], { fontSize: 12 });
    body(s, b[2], [x - 0.1, 2.85, 1.55, 0.3], { fontSize: 11.5, align: 'center', color: MUTED });
    if (i < 2) text(s, '→', [x + 1.35, 2.36, 0.5, 0.4], { fontFace: FONT, fontSize: 20, bold: true, color: BRIGHT, align: 'center' });
  });
  card(s, [0.85, 3.55, 5.75, 3.05]);
  label(s, 'Блок «Допишите»: допустимые значения КТРУ — чипы', [1.05, 3.67, 5.3, 0.3]);
  const fsz = pngSize(path.join(SRC, 'screens', 'fill_block.png')), fh = 2.38, fw = fh * fsz.w / fsz.h;
  s.addImage({ path: path.join(SRC, 'screens', 'fill_block.png'), x: 0.85 + (5.75 - fw) / 2, y: 4.07, w: fw, h: fh });
  card(s, [6.83, 1.85, 5.65, 4.75]);
  label(s, 'Пакетная проверка (CSV): ' + F.batch.rows + ' строк ≈ ' + F.batch.time.replace('≈', '').trim(), [7.03, 1.97, 5.3, 0.3]);
  const bsz = pngSize(path.join(SRC, 'screens', 'batch_view.png')), bw = 5.25, bh = bw * bsz.h / bsz.w;
  // crop starts at the «Обработано …» line (≈462 px of 1425-px-wide screenshot)
  s.addImage({ path: path.join(SRC, 'screens', 'batch_view.png'), x: 7.03, y: 2.4, w: bw, h: bh, sizing: { type: 'crop', x: 0, y: bw * 462 / bsz.w, w: bw, h: 3.05 } });
  const b = F.batch;
  body(s, [{ text: 'Код: ', options: { bold: true } }, { text: b.determined + ' определён · ' + b.ambiguous + ' неоднозначно · ' + (b.notFound ? b.notFound + ' не найден' : b.outOfScope + ' не наша категория'), options: { breakLine: true } },
    { text: 'Карточка: ', options: { bold: true } }, { text: b.complete + ' заполнена · ' + b.incomplete + ' неполная · ' + b.withErrors + ' с ошибками', options: { breakLine: true } },
    { text: 'Щелчок по строке — открыть в редакторе; выгрузка в CSV', options: { color: MUTED } }], [7.03, 5.55, 5.3, 0.95], { fontSize: 12 });
  return s;
}

function fMetrics(p, n, t) {
  const s = p.addSlide();
  chrome(s, n, t);
  headline(s, 'Код КТРУ первым: ' + M.main.top1 + ', на новых позициях — ' + M.heldOut.top1, [0.85, 1.0, 11.6, 0.6], { fontSize: 24 });
  body(s, 'Эталоны зафиксированы до прогона · два набора по ' + M.main.cases + ' позиций · источник: ' + F.source, [0.85, 1.6, 11.6, 0.35], { fontSize: 13, color: MUTED });
  const ie = M.injectedErrors;
  const tiles = [
    [M.main.top1 + ' · ' + M.heldOut.top1, 'Код на 1-м месте', 'основной / отложенный: ' + M.main.top1Pct + ' / ' + M.heldOut.top1Pct],
    [M.main.top3 + ' · ' + M.heldOut.top3, 'Код в топ-3', 'основной / отложенный: ' + M.main.top3Pct + ' / ' + M.heldOut.top3Pct],
    [F.falseAlarmsStrict, 'Ложные тревоги (строго)', 'H31 — в карточке реальная ошибка: лобзик 2,1 г'],
    [ie.caught + '*', 'Внесённые ошибки пойманы', 'единицы ' + ie.units + ', числа ' + ie.unrealistic + ', несуществующие ' + ie.nonExistent + ', опечатки ' + ie.typos],
    [F.latencyHeadline, 'Время ответа, p50', 'основной ' + F.p50.main + ', отложенный ' + F.p50.heldOut],
    [F.breakIt.passed, '«Сломай решение»', F.breakIt.pct + ': ' + F.breakIt.note]];
  tiles.forEach(function (c, i) {
    const x = 0.85 + (i % 3) * 3.94, y = 2.2 + Math.floor(i / 3) * 2.12, w = 3.75, h = 1.95;
    card(s, [x, y, w, h]);
    headline(s, c[0], [x + 0.25, y + 0.22, w - 0.5, 0.6], { fontSize: c[0].length > 14 ? 26 : 30, color: BRIGHT });
    heading(s, c[1], [x + 0.25, y + 0.92, w - 0.5, 0.3], { fontSize: 14, color: BLUE });
    body(s, c[2], [x + 0.25, y + 1.27, w - 0.5, 0.6], { fontSize: 12 });
  });
  body(s, '* ' + M.injectedCaveat.replace('набор известен разработчикам — оценка оптимистичная', 'оценка оптимистичная, набор известен разработчикам') + '. Статус верный: ' + M.main.status + ' и ' + M.heldOutStatus + '; мягкие предупреждения на чистых — ' + F.softWarnings + '.',
    [0.85, 6.5, 11.6, 0.3], { fontSize: 11.5, color: MUTED });
  return s;
}

function buildFinal() {
  setFinalTheme();
  const p = new PptxGenJS();
  p.defineLayout({ name: 'W', width: 13.333333, height: 7.5 }); p.layout = 'W';
  p.title = 'Помощник заполнения характеристик СТЕ — предзащита, Tender Hack 2026';
  p.theme = { headFontFace: FONT, bodyFontFace: FONT };
  const order = [['cover', fCover], ['how', fHow], ['diff', fDiff], ['arch', fArch], ['fill', fFill], ['metrics', fMetrics], ['team', sTeam]];
  order.forEach(function (o, i) { const s = o[1](p, i + 1, order.length); s.addNotes(NOTES.final[o[0]]); });
  return p.writeFile({ fileName: path.join(DOCS, 'presentation_final.pptx') });
}

const NOTES = require('./notes.js');
function build(variant) {
  const p = new PptxGenJS();
  p.defineLayout({ name: 'W', width: 13.333333, height: 7.5 }); p.layout = 'W';
  p.title = 'Помощник заполнения характеристик СТЕ — Tender Hack 2026';
  p.theme = { headFontFace: FONT, bodyFontFace: FONT };
  const order = variant === 'A'
    ? [['cover', sCover], ['solution', sSolution], ['bpmn', sBpmn], ['components', sComponents], ['tech', sTech], ['results', sResults], ['team', sTeam]]
    : [['cover', sCover], ['ktru', sKtru], ['solution', sSolution], ['ui', sUI], ['bpmn', sBpmn], ['components', sComponents], ['tech', sTech], ['results', sResults], ['roadmap', sRoadmap], ['team', sTeam]];
  order.forEach(function (o, i) { const s = o[1](p, i + 1, order.length); s.addNotes(NOTES[variant][o[0]] || NOTES.common[o[0]]); });
  return p.writeFile({ fileName: path.join(__dirname, variant === 'A' ? 'presentation.pptx' : 'presentation_7min.pptx') });
}
if (process.argv[2] === 'final') buildFinal().then(function () { console.log('ok final'); });
else build('A').then(function () { return build('B'); }).then(function () { console.log('ok'); });
