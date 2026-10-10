const $ = (id) => document.getElementById(id);

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
    b.onclick = () => {
      $("text").value = c.text;
      $("domain").value = c.domain_hint || "";
      run();
    };
    box.appendChild(b);
  });
}

function sourceBadge(src) {
  return `<span class="badge ${src}">${src}</span>`;
}

function render(data) {
  const status = $("status");
  status.className = `status ${data.status || "idle"}`;
  const labels = {
    ok: "Код КТРУ подобран",
    need_more: "Нужны уточнения",
    ambiguous: "Неоднозначно",
    error: "Ошибка",
  };
  status.textContent = labels[data.status] || data.status;

  const el = $("result");
  if (!data) {
    el.className = "result empty";
    el.textContent = "Результат появится здесь";
    return;
  }
  el.className = "result";

  const best = data.best_ktru
    ? `<div class="block">
        <h2>Лучший код КТРУ</h2>
        <div class="step">
          <div class="head"><span>${data.best_ktru.code}</span><span>${data.best_ktru.score}</span></div>
          <div class="cand"><b>${escapeHtml(data.best_ktru.name)}</b></div>
          ${data.best_ktru.okpd2 ? `<div class="cand">ОКПД2: ${escapeHtml(data.best_ktru.okpd2)}</div>` : ""}
        </div>
      </div>`
    : "";

  const chars = (data.characteristics || [])
    .map(
      (c) => `<div class="card-line">
        <div><b>${escapeHtml(c.canonical_name)}</b><div class="cand">${escapeHtml(c.raw_name)}</div></div>
        <div>${escapeHtml(c.value)}${c.unit ? " " + escapeHtml(c.unit) : ""}</div>
        ${sourceBadge(c.source)}
      </div>`
    )
    .join("");

  const issues = (data.issues || [])
    .map(
      (i) => `<div class="issue ${i.kind}">
        <div class="msg">${escapeHtml(i.message)}</div>
        ${i.suggestion ? `<div class="sug">→ ${escapeHtml(i.suggestion)}</div>` : ""}
      </div>`
    )
    .join("");

  const steps = (data.narrowing || [])
    .map((s) => {
      const cands = (s.top || [])
        .slice(0, 5)
        .map(
          (c) =>
            `<div class="cand"><b>${escapeHtml(c.code)}</b> · ${escapeHtml(c.name)} · ${c.score}</div>`
        )
        .join("");
      return `<div class="step">
        <div class="head"><span>${escapeHtml(s.stage)}</span><span>осталось: ${s.remaining}</span></div>
        ${s.note ? `<div class="cand">${escapeHtml(s.note)}</div>` : ""}
        ${cands}
      </div>`;
    })
    .join("");

  const next =
    data.next_steps && data.next_steps.length
      ? `<div class="block"><h2>Что сделать дальше</h2><ul class="next">${data.next_steps
          .map((x) => `<li>${escapeHtml(x)}</li>`)
          .join("")}</ul></div>`
      : "";

  el.innerHTML = `
    <div class="block">
      <h2>Распознано</h2>
      <div class="cand">Домен: <b>${escapeHtml(data.detected_domain || "—")}</b></div>
      <div class="cand">Товар: <b>${escapeHtml(data.product_guess || "—")}</b></div>
    </div>
    ${best}
    <div class="block"><h2>Унифицированные характеристики</h2><div class="kv">${chars || "<div class='cand'>нет</div>"}</div></div>
    <div class="block"><h2>Замечания</h2>${issues || "<div class='cand'>нет</div>"}</div>
    <div class="block"><h2>Сужение КТРУ</h2>${steps || "<div class='cand'>нет</div>"}</div>
    ${next}
  `;
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function run() {
  const text = $("text").value.trim();
  if (!text) return;
  $("status").className = "status idle";
  $("status").textContent = "Считаем…";
  $("run").disabled = true;
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        domain_hint: $("domain").value || null,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Ошибка API");
    render(data);
  } catch (e) {
    $("status").className = "status error";
    $("status").textContent = "Ошибка";
    $("result").innerHTML = `<div class="issue error"><div class="msg">${escapeHtml(e.message)}</div></div>`;
  } finally {
    $("run").disabled = false;
  }
}

$("run").onclick = run;
$("clear").onclick = () => {
  $("text").value = "";
  $("domain").value = "";
  $("status").className = "status idle";
  $("status").textContent = "Ожидание ввода";
  $("result").className = "result empty";
  $("result").textContent = "Результат появится здесь";
};

loadDemos().catch(console.error);
