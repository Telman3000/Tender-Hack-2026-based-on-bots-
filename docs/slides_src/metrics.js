/* All metric numbers used in the decks. Edit here, then run `node deck.js`. */
module.exports = {
  versionNote: 'Цифры на текущей версии',
  // Основной набор (45 кейсов)
  main: { cases: 45, top1: '44/45', top1Pct: '98%', top3: '45/45', top3Pct: '100%' },
  // Отложенный набор (45 новых позиций, код не подстраивался)
  heldOut: { cases: 45, top1: '43/45', top1Pct: '96%', top3: '44/45', top3Pct: '98%' },
  heldOutStatus: '43/45',
  heldOutStatusPct: '96%',
  heldOutByDomain: { furniture: '15/15', tools: '15/15', clothing: '13/15' },
  falseAlarms: '1/42',
  // Внесённые ошибки (на слайды не выводятся; только для справки)
  injectedErrors: { caught: '19/30', units: '8/8', unrealistic: '7/8', typos: '4/7', nonExistent: '0/7' },
  // Скорость и инфраструктура
  latencyMedian: '~50 мс',
  latencyP95: '99–164 мс',
  indexBuild: '~100 с',
  autotests: '58',
  ktruItems: '3391',
  loadParallel: '50',
  funnelOutput: 'на выходе группа из 2–3 вариаций'
};
