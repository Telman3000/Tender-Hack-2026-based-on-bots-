/* All metric numbers used in the decks. Edit here, then run `node deck.js`.
   FINAL QA: build main + core 9e6d6a9 + ui 8c1c598, two runs matched. */
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
  latencyP95: '~160–190 мс',
  indexBuild: '~100 с',
  autotests: '62/62',
  ktruItems: '3391',
  loadParallel: '50',
  funnelOutput: 'на выходе группа из 2–3 вариаций',
  // Финальная предзащита (presentation_final.pptx). Источник: qa/metrics_slide.md на origin/feature/qa
  final: {
    source: 'qa/metrics_slide.md (main 7aa9939)',
    falseAlarmsStrict: '1/42',
    softWarnings: '4/42',
    latencyHeadline: 'медиана < 0,1 с',
    p50Range: '50–100 мс',
    p50: { main: '53–98 мс', heldOut: '49–60 мс' },     // 2 прогона
    p95: { main: '126–194 мс', heldOut: '102–138 мс' },
    breakIt: { passed: '32/32', pct: '100%', note: '0 ответов 500, 0 ошибок JS' },
    howFunnel: '1309 → 3',                                 // TO42, инструменты
    batch: { rows: 13, time: '≈1,3 с', timeSpoken: 'около 1,3 секунды', determined: 9, ambiguous: 2, notFound: 0, outOfScope: 2, complete: 4, incomplete: 8, withErrors: 1 } // docs/demo_batch.csv, screens/batch_view.png (main c6a89cd)
  }
};
