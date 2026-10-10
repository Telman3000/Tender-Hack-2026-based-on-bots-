// jsdom: юнит-тесты CSV + смоук UI против живого сервера.
// Запуск: NODE_PATH=<каталог с jsdom> node frontend/tests/ui_smoke.cjs http://127.0.0.1:8791
const { JSDOM, VirtualConsole } = require("jsdom");
const fs = require("fs"), path = require("path"), assert = require("assert");
const BASE = process.argv[2] || "http://127.0.0.1:8791";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const errors = [], net = [];
async function boot() {
  const html = await (await fetch(BASE + "/")).text();
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => errors.push("jsdomError: " + e.message));
  vc.on("error", (...a) => errors.push("console.error: " + a.join(" ")));
  const dom = new JSDOM(html, { url: BASE + "/", runScripts: "dangerously", resources: "usable", pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      w.fetch = async (u, o) => { const url = new URL(u, BASE).href; const r = await fetch(url, o); net.push([r.status, (o && o.method) || "GET", url]); return r; };
      w.TextDecoder = TextDecoder; w.performance = performance;
      w.addEventListener("error", (e) => errors.push("window.error: " + e.message));
    } });
  for (let i = 0; i < 100 && !(dom.window.__ktru && dom.window.document.querySelector("#demos .chip")); i++) await sleep(100);
  return dom;
}
async function until(fn, ms = 8000) { for (let t = 0; t < ms; t += 100) { if (fn()) return true; await sleep(100); } return false; }
(async () => {
  const dom = await boot(); const w = dom.window, d = w.document, K = w.__ktru;
  assert(K, "app loaded");
  // ---- CSV parse
  const J = (v) => JSON.parse(JSON.stringify(v)); const P = (t) => J(K.parseNames(t));
  assert.deepStrictEqual(P("Стол письменный; цвет белый; 1200х600"), ["Стол письменный; цвет белый; 1200х600"]);
  assert.deepStrictEqual(P("\uFEFFНаименование\r\nСтол письменный; цвет белый; 1200х600\r\nСтул, чёрный\r\n"), ["Стол письменный; цвет белый; 1200х600", "Стул, чёрный"]);
  assert.deepStrictEqual(P('"Стол; белый ""Люкс"""\n"Шкаф,\nдвухстворчатый"'), ['Стол; белый "Люкс"', "Шкаф,\nдвухстворчатый"]);
  assert.deepStrictEqual(P("id;Наименование;цена\n1;Стол письменный;100\n2;\"Стул; кожа\";50"), ["Стол письменный", "Стул; кожа"]);
  assert.deepStrictEqual(P("name,qty\n\"Стол, белый\",2"), ["Стол, белый"]);
  // ---- export round-trip
  const tricky = ['Стол; белый "Люкс"', "Шкаф,\nдвухстворчатый", "Стол письменный; цвет белый; 1200х600"];
  K.batch.results = tricky.map((t, i) => ({ id: String(i + 1), text: t, code: "31.01", name: 'X; "y"', code_status: "determined", card_status: "complete", missing: 0, notes: "a; b", ms: 1, chars: "k=v; z" }));
  const csv = K.buildExportCsv();
  const recs = J(K.csvRecords(csv.replace(/^\uFEFF/, ""), ";").filter((r) => r.cells.length > 1));
  assert.deepStrictEqual(recs.slice(1).map((r) => r.cells[1]), tricky, "round-trip text");
  assert.strictEqual(recs[1].cells[3], 'X; "y"');
  console.log("CSV tests: OK");
  // ---- smoke single
  const run = async (txt) => { const before = d.getElementById("result").innerHTML; d.getElementById("text").value = txt;
    d.getElementById("text").dispatchEvent(new w.Event("input")); d.getElementById("run").click();
    await until(() => d.getElementById("result").innerHTML !== before && !/загруж|провер/i.test(d.getElementById("status").textContent || ""));
    await sleep(600); return d.getElementById("status").textContent.trim() + " | " + d.getElementById("result").textContent.replace(/\s+/g, " ").slice(0, 120); };
  console.log("FU19:", await run("Кресло офисное обивка ткань цвет черный высота 1080 мм ширина 650 мм глубина 450 мм"));
  console.log("TO42:", await run("Ключ гаечный 170х190 мм длина 27 м"));
  console.log("TO37:", await run("Ключ"));
  const chip = d.querySelector("#result [data-fill]");
  console.log("TO37 chip:", chip ? chip.textContent.trim() : "NONE");
  if (chip) { const b = d.getElementById("result").innerHTML; chip.click(); await until(() => d.getElementById("result").innerHTML !== b); await sleep(1500); console.log("  after chip:", d.getElementById("status").textContent.trim()); }
  console.log("x:", await run("x"));
  d.getElementById("text").value = ""; d.getElementById("run").click(); await sleep(500);
  console.log("empty:", d.getElementById("status").textContent.trim(), "|", d.getElementById("result").textContent.trim().slice(0, 60));
  // ---- batch
  K.showTab("batch");
  const names = K.parseNames(K.decodeCsv(fs.readFileSync(path.join(__dirname, "..", "..", "docs", "demo_batch.csv"))));
  await K.runBatch(names);
  console.log("batch:", names.length, "rows;", d.getElementById("batchMode").textContent, "|", d.getElementById("summary").textContent.replace(/\s+/g, " ").trim());
  const bad = net.filter((n) => n[0] >= 400);
  console.log("requests:", net.length, "4xx/5xx:", bad.length, bad.map((b) => b.join(" ")).join(", "));
  console.log("batch probes:", net.filter((n) => /analyze\/batch/.test(n[2])).length, "openapi:", net.filter((n) => /openapi/.test(n[2])).length);
  console.log("JS errors:", errors.length, errors.join(" || "));
  if (bad.length || errors.length) process.exitCode = 1;
  w.close();
})().catch((e) => { console.error("FAIL", e); process.exit(1); });
