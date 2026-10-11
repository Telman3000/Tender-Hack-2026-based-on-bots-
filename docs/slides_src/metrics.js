/* All metric numbers used in the decks. Edit here, then run `node deck.js`.
   FINAL QA: main ab39ee1 (qa/summary.md, acceptance core 24411af + ui 4d6ae93, 2 runs). */
module.exports = {
  versionNote: 'Цифры на текущей версии',
  // Основной набор (45 кейсов)
  main: { cases: 45, top1: '44/45', top1Pct: '98%', top3: '45/45', top3Pct: '100%', status: '45/45', statusPct: '100%' },
  // Отложенный набор (45 новых позиций, код не подстраивался)
  heldOut: { cases: 45, top1: '43/45', top1Pct: '96%', top3: '44/45', top3Pct: '98%' },
  heldOutStatus: '43/45',
  heldOutStatusPct: '96%',
  heldOutByDomain: { furniture: '15/15', tools: '15/15', clothing: '13/15' }, // код на 1-м месте
  falseAlarms: '1/42',
  heldOutStatusByDomain: { furniture: '15/15', tools: '14/15', clothing: '14/15' },
  falseAlarmsSlide: 'Ложные тревоги 1/42 — и эта настоящая ошибка в карточке (2,1 г)',
  weakSpot: 'путаем близкие товары (брюки, резиновые сапоги); 30/30 по ошибкам — оптимистичная оценка',
  falseAlarmsNote: 'H31 — на деле реальная ошибка карточки: лобзик весом 2,1 г',
  // Внесённые ошибки — набор известен разработчикам, оценка оптимистичная
  injectedErrors: { caught: '30/30', units: '8/8', unrealistic: '8/8', nonExistent: '7/7', typos: '7/7' },
  injectedCaveat: 'набор известен разработчикам — оценка оптимистичная',
  // Скорость и инфраструктура
  latencyMedian: '~50 мс',
  latencyP95: '~80–105 мс',
  indexBuild: '~60 с',
  autotests: '136/136',
  ktruItems: '3030',
  loadParallel: '50',
  funnelOutput: 'на выходе группа из 2–3 вариаций',
  // Финальная предзащита (presentation_final.pptx). Источник: qa/metrics_slide.md на origin/feature/qa
  final: {
    source: 'qa/metrics_slide.md',
    build: 'Версия: main ab39ee1',
    falseAlarmsStrict: '1/42',
    softWarnings: '3/42',
    latencyHeadline: 'медиана < 0,1 с',
    p50Range: '50–100 мс',
    p50: { main: '51–54 мс', heldOut: '48–54 мс' },     // 2 прогона
    p95: { main: '102–104 мс', heldOut: '78–93 мс' },
    breakIt: { passed: '32/32', pct: '100%', note: '0 ответов 500, 0 ошибок JS' },
    howFunnel: '1309 → 3',                                 // TO42, инструменты
    batch: { rows: 13, time: '~0,5 с', timeSpoken: 'около 0,5 секунды', determined: 9, ambiguous: 2, notFound: 0, outOfScope: 2, complete: 4, incomplete: 8, withErrors: 1 } // docs/demo_batch.csv, screens/batch_view.png (main c6a89cd)
  }
};
