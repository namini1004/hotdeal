const fs = require('fs');
const path = require('path');

const FEED_FILES = [
  path.join(process.cwd(), 'assets', 'ppomppu_hotdeals_2days.json'),
  path.join(process.cwd(), 'assets', 'quasar_hotdeals_2days.json'),
  path.join(process.cwd(), 'assets', 'fmkorea_hotdeals_2days.json'),
  path.join(process.cwd(), 'assets', 'ruliweb_hotdeals_1day.json'),
];
const FEED_SOURCES = ['ppomppu', 'quasar', 'fmkorea', 'ruliweb'];
const FEED_SOURCE_LIMIT = 900;
const FEED_LOOKBACK_HOURS = 48;
const FEED_FUTURE_SKEW_MINUTES = 10;
const FEED_PAGE_COLUMNS = [
  'id',
  'title',
  'area',
  'dist',
  'time',
  'price',
  'category',
  'desc',
  'img',
  'detail_img',
  'source_link',
  'source_post_id',
  'buy_link',
  'likes',
  'dislikes',
  'views',
  'comments',
  'comment_signal_score',
  'positive_comment_signals',
  'negative_comment_signals',
  'date',
  'registered_at',
  'source',
  'edited',
  'updated_at',
].join(',');
const FEED_SCORE_COLUMNS = [
  'source',
  'views',
  'comments',
  'likes',
  'dislikes',
  'comment_signal_score',
  'positive_comment_signals',
  'negative_comment_signals',
  'registered_at',
].join(',');

const HOT_SCORE_CONFIG = {
  commentWeight: 1.8,
  recencyWeight: 0.65,
  likeWeight: 1.2,
  dislikeWeight: 4.0,
  commentSignalWeight: 0.75,
  metricWeights: {
    views: 1.0,
    comments: 1.8,
    likes: 1.2,
  },
  sourceRelativeWeight: 0.85,
  globalAbsoluteWeight: 0.15,
  engagementTemperatureWeight: 0.88,
  recencyTemperatureWeight: 0.12,
  globalEliteThreshold: 95,
  globalEliteMaxBonus: 8,
  minimumMetricSamples: 8,
  minimumMetricNonZero: 5,
  minimumMetricCoverage: 0.2,
  minimumLogStdDev: 0.08,
  zScoreClamp: 3,
  qualitySignalTemperatureWeight: 5,
  qualitySignalTemperatureCap: 12,
  dislikeTemperatureWeight: 8,
  recencyWindowHours: 48,
  hotBoostHours: 3,
  negativeSignalCapThreshold: 3,
  negativeSignalTemperatureCap: 50,
  contaminatedNegativeSignalRate: 0.6,
};

const TEMPERATURE_MODEL_VERSION = 2;
const TEMPERATURE_METRICS = ['views', 'comments', 'likes'];

function parseNumericPriceValue(priceText = '') {
  const s = String(priceText || '').replace(/\s+/g, '');
  const num = Number((s.match(/[0-9][0-9,]*/) || ['0'])[0].replace(/,/g, ''));
  if (!num) return 0;
  if (s.includes('만원')) return num * 10000;
  if (s.includes('천원')) return num * 1000;
  return num;
}

function extractBestPriceFromText(text = '') {
  let s = String(text || '');
  // '919 000원'처럼 공백 천단위 표기를 먼저 보정
  s = s.replace(/(?<!\d)(\d{1,3})\s{1,2}(\d{3})(\s*원)/g, '$1,$2$3');
  const candidates = [];

  const pushCandidate = (raw) => {
    const normalized = String(raw || '')
      .replace(/\s+/g, '')
      .replace(/[.,;:!?]+$/g, '');
    if (!normalized) return;
    const value = parseNumericPriceValue(normalized);
    const hasComma = normalized.includes(',');
    candidates.push({ raw: normalized, value, hasComma });
  };

  // 1) 원/천원/만원 계열
  let m;
  const wonRegex = /([0-9][0-9,]*\s*(?:만원대|천원대|원대|만원|천원|원))(?![가-힣A-Za-z])/g;
  while ((m = wonRegex.exec(s)) !== null) pushCandidate(m[1]);

  // 2) ₩/￦ 통화기호 + 숫자 (예: ￦68,400)
  const symbolRegex = /([₩￦]\s*[0-9][0-9,]{2,})(?![0-9])/g;
  while ((m = symbolRegex.exec(s)) !== null) {
    const numeric = m[1].replace(/[₩￦]/g, '').replace(/[\s.,;:!?]+$/g, '').trim();
    const withWon = `${numeric}원`;
    pushCandidate(withWon);
  }

  // 3) 통화기호/원 없이 천단위 콤마 숫자 (예: 68,400)
  const commaNumberRegex = /(^|[^0-9])([0-9]{1,3}(?:,[0-9]{3})+)(?![0-9])/g;
  while ((m = commaNumberRegex.exec(s)) !== null) {
    pushCandidate(`${m[2]}원`);
  }

  if (!candidates.length) return '';

  const over1k = candidates.filter((c) => c.value >= 1000);
  const pool = over1k.length ? over1k : candidates;

  pool.sort((a, b) => {
    if (Number(b.hasComma) !== Number(a.hasComma)) return Number(b.hasComma) - Number(a.hasComma);
    if (b.value !== a.value) return b.value - a.value;
    return b.raw.length - a.raw.length;
  });
  return pool[0].raw;
}

function inferKeywordPrice(title = '', desc = '', currentPrice = '') {
  const t = String(title || '');
  const d = String(desc || '');
  const p = String(currentPrice || '').trim();

  const fromTitle = extractBestPriceFromText(t);
  if (fromTitle) return fromTitle;

  if (!p || p === '가격 정보 확인') {
    const fromDesc = extractBestPriceFromText(d);
    if (fromDesc) return fromDesc;
  }

  if ((/무료/.test(t) || /무료/.test(d)) && (!p || p === '가격 정보 확인')) return '무료';
  if (!p || p === '가격 정보 확인') {
    if (/다양/.test(t) || /다양/.test(d)) return '다양';
  }
  return p;
}

function normalizeUserImageUrl(value = '') {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (!/^https?:\/\//i.test(raw)) return raw;
  try {
    const url = new URL(raw);
    if (/wsrv\.nl$/i.test(url.hostname)) return raw;
    if (/\.supabase\.co$/i.test(url.hostname) && url.pathname.startsWith('/storage/v1/object/public/')) return raw;
    return `https://wsrv.nl/?url=${encodeURIComponent(url.host + url.pathname + url.search)}&w=640&h=640&fit=inside&output=webp`;
  } catch (_) {
    return raw;
  }
}

function parseDateMs(value) {
  if (!value) return 0;
  const ms = Date.parse(String(value));
  return Number.isFinite(ms) ? ms : 0;
}

function isFeedTimestampInWindow(item = {}, nowMs = Date.now()) {
  const registeredMs = parseDateMs(item.registeredAt || item.date || '');
  if (!registeredMs) return false;
  const minMs = nowMs - FEED_LOOKBACK_HOURS * 60 * 60 * 1000;
  const maxMs = nowMs + FEED_FUTURE_SKEW_MINUTES * 60 * 1000;
  return registeredMs >= minMs && registeredMs <= maxMs;
}

function computeHotScore(item, nowMs, sourceAvg = { views: 0, comments: 0 }) {
  const views = Math.max(0, Number(item.views || 0));
  const comments = Math.max(0, Number(item.comments || 0));
  const likes = Math.max(0, Number(item.likes || 0));
  const dislikes = Math.max(0, Number(item.dislikes || 0));
  const commentSignalScore = Math.max(-60, Math.min(16, Number(item.commentSignalScore || 0)));

  const registeredMs = parseDateMs(item.registeredAt || item.date || '');
  const hoursSincePost = registeredMs
    ? Math.max(0, (nowMs - registeredMs) / (1000 * 60 * 60))
    : HOT_SCORE_CONFIG.recencyWindowHours;
  const freshness = Math.max(0, 1 - hoursSincePost / HOT_SCORE_CONFIG.recencyWindowHours);

  const avgViews = Math.max(1, Number(sourceAvg.views || 1));
  const avgComments = Math.max(1, Number(sourceAvg.comments || 1));
  const viewDeficit = Math.max(0, Math.min(1, (avgViews - views) / avgViews));
  const commentDeficit = Math.max(0, Math.min(1, (avgComments - comments) / avgComments));
  const scarcityBoost = 0.2 + 0.8 * ((viewDeficit + commentDeficit) / 2);
  const ultraFreshBoost = hoursSincePost <= HOT_SCORE_CONFIG.hotBoostHours ? 2 : 1;

  const viewScore = Math.log10(views + 1);
  const commentScore = Math.log10(comments + 1) * HOT_SCORE_CONFIG.commentWeight;
  const likeScore = Math.log10(likes + 1) * HOT_SCORE_CONFIG.likeWeight;
  const dislikePenalty = Math.log10(dislikes + 1) * HOT_SCORE_CONFIG.dislikeWeight;
  const commentSignalScoreBoost = commentSignalScore * HOT_SCORE_CONFIG.commentSignalWeight;
  const recencyScore = HOT_SCORE_CONFIG.recencyWeight * freshness * scarcityBoost * ultraFreshBoost;
  return viewScore + commentScore + likeScore - dislikePenalty + commentSignalScoreBoost + recencyScore;
}

function shouldCapNegativeTemperature(item = {}) {
  const negativeCommentSignals = Math.max(0, Number(item.negativeCommentSignals || 0));
  const dislikes = Math.max(0, Number(item.dislikes || 0));
  return (
    negativeCommentSignals >= HOT_SCORE_CONFIG.negativeSignalCapThreshold ||
    dislikes >= HOT_SCORE_CONFIG.negativeSignalCapThreshold
  );
}

function quantile(values = [], percentile = 0.5) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const position = Math.max(0, Math.min(sorted.length - 1, (sorted.length - 1) * percentile));
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  const fraction = position - lower;
  return sorted[lower] + (sorted[upper] - sorted[lower]) * fraction;
}

function buildMetricStats(values = []) {
  const rawValues = values.map((value) => Math.max(0, Number(value || 0)));
  const sampleCount = rawValues.length;
  const nonZeroCount = rawValues.filter((value) => value > 0).length;
  const coverage = sampleCount ? nonZeroCount / sampleCount : 0;
  const rawMean = sampleCount
    ? rawValues.reduce((sum, value) => sum + value, 0) / sampleCount
    : 0;
  const rawVariance = sampleCount
    ? rawValues.reduce((sum, value) => sum + ((value - rawMean) ** 2), 0) / sampleCount
    : 0;
  const logValues = rawValues.map((value) => Math.log1p(value));
  const logMean = sampleCount
    ? logValues.reduce((sum, value) => sum + value, 0) / sampleCount
    : 0;
  const logVariance = sampleCount
    ? logValues.reduce((sum, value) => sum + ((value - logMean) ** 2), 0) / sampleCount
    : 0;
  const logStdDev = Math.sqrt(logVariance);
  const usable = (
    sampleCount >= HOT_SCORE_CONFIG.minimumMetricSamples &&
    nonZeroCount >= HOT_SCORE_CONFIG.minimumMetricNonZero &&
    coverage >= HOT_SCORE_CONFIG.minimumMetricCoverage &&
    logStdDev >= HOT_SCORE_CONFIG.minimumLogStdDev
  );

  return {
    sampleCount,
    nonZeroCount,
    coverage,
    rawMean,
    rawVariance,
    rawStdDev: Math.sqrt(rawVariance),
    p50: quantile(rawValues, 0.5),
    p75: quantile(rawValues, 0.75),
    p90: quantile(rawValues, 0.9),
    p95: quantile(rawValues, 0.95),
    max: rawValues.length ? Math.max(...rawValues) : 0,
    logMean,
    logVariance,
    logStdDev,
    usable,
  };
}

function buildSignedMetricStats(values = []) {
  const numeric = values.map((value) => Number(value || 0)).filter(Number.isFinite);
  const sampleCount = numeric.length;
  const mean = sampleCount ? numeric.reduce((sum, value) => sum + value, 0) / sampleCount : 0;
  const variance = sampleCount
    ? numeric.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / sampleCount
    : 0;
  const stdDev = Math.sqrt(variance);
  return {
    sampleCount,
    mean,
    variance,
    stdDev,
    usable: sampleCount >= HOT_SCORE_CONFIG.minimumMetricSamples && stdDev >= 1,
  };
}

function clampZScore(value) {
  return Math.max(-HOT_SCORE_CONFIG.zScoreClamp, Math.min(HOT_SCORE_CONFIG.zScoreClamp, value));
}

function metricZScore(value, stats = {}) {
  if (!stats.usable || !Number.isFinite(stats.logStdDev) || stats.logStdDev <= 0) return null;
  return clampZScore((Math.log1p(Math.max(0, Number(value || 0))) - stats.logMean) / stats.logStdDev);
}

function normalCdf(value) {
  const z = clampZScore(Number(value || 0)) / Math.sqrt(2);
  const sign = z < 0 ? -1 : 1;
  const x = Math.abs(z);
  const t = 1 / (1 + 0.3275911 * x);
  const polynomial = (
    0.254829592 * t -
    0.284496736 * (t ** 2) +
    1.421413741 * (t ** 3) -
    1.453152027 * (t ** 4) +
    1.061405429 * (t ** 5)
  );
  const erf = sign * (1 - polynomial * Math.exp(-(x ** 2)));
  return 0.5 * (1 + erf);
}

function percentileTemperature(zScore) {
  return normalCdf(zScore) * 100;
}

function empiricalPercentile(value, sortedValues = []) {
  if (sortedValues.length <= 1) return 50;
  let lower = 0;
  while (lower < sortedValues.length && sortedValues[lower] < value) lower += 1;
  let upper = lower;
  while (upper < sortedValues.length && sortedValues[upper] === value) upper += 1;
  const midRank = (lower + Math.max(lower, upper - 1)) / 2;
  return (midRank / (sortedValues.length - 1)) * 100;
}

function compositeMetricZ(item = {}, metricStats = {}, sourceMetricStats = null) {
  let weightedScore = 0;
  let squaredWeight = 0;
  let metricCount = 0;

  for (const metric of TEMPERATURE_METRICS) {
    if (sourceMetricStats && !sourceMetricStats[metric]?.usable) continue;
    const zScore = metricZScore(item[metric], metricStats[metric]);
    if (zScore === null) continue;
    const weight = HOT_SCORE_CONFIG.metricWeights[metric] || 1;
    weightedScore += zScore * weight;
    squaredWeight += weight ** 2;
    metricCount += 1;
  }

  return {
    zScore: squaredWeight > 0 ? clampZScore(weightedScore / Math.sqrt(squaredWeight)) : 0,
    metricCount,
  };
}

function sourceMetricAverages(list = []) {
  const n = Math.max(1, list.length);
  return {
    views: list.reduce((sum, item) => sum + Math.max(0, Number(item.views || 0)), 0) / n,
    comments: list.reduce((sum, item) => sum + Math.max(0, Number(item.comments || 0)), 0) / n,
  };
}

function buildTemperatureProfile(items = [], nowMs = Date.now()) {
  const bySource = new Map();

  for (const item of items) {
    const source = item.source || 'feed';
    if (!bySource.has(source)) bySource.set(source, []);
    bySource.get(source).push(item);
  }

  const avgBySource = new Map();
  const statsBySource = new Map();
  for (const [source, list] of bySource.entries()) {
    avgBySource.set(source, sourceMetricAverages(list));
    const metrics = {};
    for (const metric of TEMPERATURE_METRICS) {
      metrics[metric] = buildMetricStats(list.map((item) => item[metric]));
    }
    statsBySource.set(source, {
      sampleCount: list.length,
      metrics,
      qualitySignal: buildSignedMetricStats(list.map((item) => item.commentSignalScore)),
      negativeCapRate: list.length
        ? list.filter((item) => shouldCapNegativeTemperature(item)).length / list.length
        : 0,
    });
    const sourceStats = statsBySource.get(source);
    sourceStats.qualitySignalsContaminated = (
      list.length >= HOT_SCORE_CONFIG.minimumMetricSamples &&
      sourceStats.negativeCapRate >= HOT_SCORE_CONFIG.contaminatedNegativeSignalRate
    );
  }

  const globalMetricStats = {};
  for (const metric of TEMPERATURE_METRICS) {
    const eligibleValues = items
      .filter((item) => statsBySource.get(item.source || 'feed')?.metrics?.[metric]?.usable)
      .map((item) => item[metric]);
    globalMetricStats[metric] = buildMetricStats(eligibleValues);
  }

  for (const [source, list] of bySource.entries()) {
    const sourceStats = statsBySource.get(source);
    sourceStats.compositeZScores = list
      .map((item) => compositeMetricZ(item, sourceStats.metrics).zScore)
      .sort((a, b) => a - b);
  }

  return {
    version: TEMPERATURE_MODEL_VERSION,
    nowMs,
    avgBySource,
    statsBySource,
    globalMetricStats,
  };
}

function computeTemperatureComponents(item = {}, profile = buildTemperatureProfile([item])) {
  const source = item.source || 'feed';
  const sourceStats = profile.statsBySource.get(source) || { sampleCount: 0, metrics: {} };
  const sourceComposite = compositeMetricZ(item, sourceStats.metrics);
  const globalComposite = compositeMetricZ(item, profile.globalMetricStats, sourceStats.metrics);
  const sourceRelativeTemperature = empiricalPercentile(
    sourceComposite.zScore,
    sourceStats.compositeZScores || [],
  );
  const globalAbsoluteTemperature = globalComposite.metricCount
    ? percentileTemperature(globalComposite.zScore)
    : sourceRelativeTemperature;
  const engagementTemperature = (
    sourceRelativeTemperature * HOT_SCORE_CONFIG.sourceRelativeWeight +
    globalAbsoluteTemperature * HOT_SCORE_CONFIG.globalAbsoluteWeight
  );
  const globalEliteBonus = globalAbsoluteTemperature > HOT_SCORE_CONFIG.globalEliteThreshold
    ? (
      (globalAbsoluteTemperature - HOT_SCORE_CONFIG.globalEliteThreshold) /
      (100 - HOT_SCORE_CONFIG.globalEliteThreshold)
    ) * HOT_SCORE_CONFIG.globalEliteMaxBonus
    : 0;

  const registeredMs = parseDateMs(item.registeredAt || item.date || '');
  const hoursSincePost = registeredMs
    ? Math.max(0, (profile.nowMs - registeredMs) / (1000 * 60 * 60))
    : HOT_SCORE_CONFIG.recencyWindowHours;
  const freshness = Math.max(0, 1 - hoursSincePost / HOT_SCORE_CONFIG.recencyWindowHours);
  const recencyTemperature = freshness * 100;
  const qualityStats = sourceStats.qualitySignal || {};
  const qualitySignalZ = qualityStats.usable
    ? clampZScore((Number(item.commentSignalScore || 0) - qualityStats.mean) / qualityStats.stdDev)
    : 0;
  const commentQualityAdjustment = Math.max(
    -HOT_SCORE_CONFIG.qualitySignalTemperatureCap,
    Math.min(
      HOT_SCORE_CONFIG.qualitySignalTemperatureCap,
      qualitySignalZ * HOT_SCORE_CONFIG.qualitySignalTemperatureWeight,
    ),
  );
  const qualityAdjustment = (
    commentQualityAdjustment -
    Math.log1p(Math.max(0, Number(item.dislikes || 0))) * HOT_SCORE_CONFIG.dislikeTemperatureWeight
  );
  const temperature = (
    engagementTemperature * HOT_SCORE_CONFIG.engagementTemperatureWeight +
    recencyTemperature * HOT_SCORE_CONFIG.recencyTemperatureWeight +
    qualityAdjustment +
    globalEliteBonus
  );
  const blendedZ = (
    sourceComposite.zScore * HOT_SCORE_CONFIG.sourceRelativeWeight +
    globalComposite.zScore * HOT_SCORE_CONFIG.globalAbsoluteWeight
  );

  return {
    temperature,
    sourceRelativeTemperature,
    globalAbsoluteTemperature,
    engagementTemperature,
    recencyTemperature,
    qualityAdjustment,
    qualitySignalZ,
    globalEliteBonus,
    sourceZScore: sourceComposite.zScore,
    globalZScore: globalComposite.zScore,
    blendedZ,
    metricCount: sourceComposite.metricCount,
  };
}

function applyTemperatureProfile(items = [], profile = buildTemperatureProfile(items)) {
  return items.map((item) => {
    const sourceStats = profile.statsBySource.get(item.source || 'feed') || {};
    const components = computeTemperatureComponents(item, profile);
    let clamped = Math.max(0, Math.min(100, Math.round(components.temperature)));
    const isFree = String(item.price || '').trim() === '무료';
    if (isFree) {
      // 무료 딜은 0~100 정규화 결과를 80~100 구간으로 재매핑
      clamped = Math.max(80, Math.min(100, Math.round(80 + clamped * 0.2)));
    }
    if (!sourceStats.qualitySignalsContaminated && shouldCapNegativeTemperature(item)) {
      clamped = Math.min(clamped, HOT_SCORE_CONFIG.negativeSignalTemperatureCap);
    }

    return { ...item, hotScore: Number(components.blendedZ.toFixed(4)), temperature: clamped };
  });
}

function applyTemperatureNormalization(items = []) {
  return applyTemperatureProfile(items, buildTemperatureProfile(items));
}

function normalizeFeedItems(items = []) {
  return items.map((item, idx) => {
    const source = item.source || 'feed';
    const title = item.title || '제목 없음';
    let price = item.price || '';

    if (!price && ['ppomppu', 'fmkorea', 'ruliweb'].includes(source)) {
      price = extractBestPriceFromText(title);
    }
    price = inferKeywordPrice(title, item.desc || '', price);

    return {
      id: String(item.id ?? idx + 1),
      title,
      area: item.area || '뽐뿌 핫딜',
      dist: item.dist || '기타',
      time: item.time || item.date || '',
      price: price || (source === 'ppomppu' ? '' : '가격 정보 확인'),
      category: item.category || '기타',
      desc: item.desc || '',
      img: item.img || '',
      detailImg: item.detailImg || item.detail_img || item.img || '',
      sourceLink: item.sourceLink || '',
      buyLink: item.buyLink || '',
      likes: Number(item.likes || 0),
      dislikes: Number(item.dislikes || 0),
      views: Number(item.views || 0),
      comments: Number(item.comments || 0),
      commentSignalScore: Number(item.commentSignalScore || item.comment_signal_score || 0),
      positiveCommentSignals: Number(item.positiveCommentSignals || item.positive_comment_signals || 0),
      negativeCommentSignals: Number(item.negativeCommentSignals || item.negative_comment_signals || 0),
      date: item.date || '',
      registeredAt: item.registeredAt || '',
      source,
      edited: Boolean(item.edited),
    };
  });
}

function readFeedItemsFromFiles() {
  const merged = [];
  for (const feedFile of FEED_FILES) {
    try {
      const raw = fs.readFileSync(feedFile, 'utf-8');
      const json = JSON.parse(raw);
      merged.push(...normalizeFeedItems(json.items || json.grouped?.today || []));
    } catch (_) {
      // ignore missing/invalid feed file
    }
  }
  return applyTemperatureNormalization(merged.filter((item) => isFeedTimestampInWindow(item)));
}

function normalizeFeedDbRow(row = {}) {
  const img = normalizeUserImageUrl(row.img || '');
  const detailImg = normalizeUserImageUrl(row.detail_img || row.img || '');
  return {
    id: String(row.id || ''),
    title: row.title || '제목 없음',
    area: row.area || '뽐뿌 핫딜',
    dist: row.dist || '기타',
    time: row.time || row.date || '',
    price: inferKeywordPrice(row.title || '', row.desc || '', row.price || '') || '가격 정보 확인',
    category: row.category || '기타',
    desc: row.desc || '',
    img,
    detailImg: detailImg || img,
    sourceLink: row.source_link || '',
    sourcePostId: row.source_post_id || '',
    buyLink: row.buy_link || '',
    likes: Number(row.likes || 0),
    dislikes: Number(row.dislikes || 0),
    views: Number(row.views || 0),
    comments: Number(row.comments || 0),
    temperature: Number(row.manual_temperature ?? row.temperature ?? 100),
    manualTemperature: Number(row.manual_temperature ?? row.temperature ?? 100),
    commentSignalScore: Number(row.comment_signal_score || 0),
    positiveCommentSignals: Number(row.positive_comment_signals || 0),
    negativeCommentSignals: Number(row.negative_comment_signals || 0),
    date: row.date || '',
    registeredAt: row.registered_at || '',
    source: row.source || 'feed',
    edited: Boolean(row.edited),
    updatedAt: row.updated_at || '',
  };
}

function normalizeFeedScoreRow(row = {}) {
  return {
    source: row.source || 'feed',
    views: Number(row.views || 0),
    comments: Number(row.comments || 0),
    likes: Number(row.likes || 0),
    dislikes: Number(row.dislikes || 0),
    commentSignalScore: Number(row.comment_signal_score || 0),
    positiveCommentSignals: Number(row.positive_comment_signals || 0),
    negativeCommentSignals: Number(row.negative_comment_signals || 0),
    registeredAt: row.registered_at || '',
  };
}

function canonicalFeedKey(item = {}) {
  const source = item.source || 'feed';
  const sourceLink = item.sourceLink || '';
  if (item.sourcePostId) return `${source}::post:${item.sourcePostId}`;
  if (source === 'ppomppu') {
    const noMatch = String(sourceLink).match(/[?&]no=(\d+)/);
    if (noMatch) return `${source}::no:${noMatch[1]}`;
  }
  if (source === 'fmkorea') {
    const docMatch = String(sourceLink).match(/[?&]document_srl=(\d+)/);
    if (docMatch) return `${source}::doc:${docMatch[1]}`;
    const idMatch = String(sourceLink).match(/fmkorea\.com\/(\d+)/);
    if (idMatch) return `${source}::doc:${idMatch[1]}`;
  }
  if (source === 'quasar') {
    const idMatch = String(sourceLink).match(/\/views\/(\d+)/);
    if (idMatch) return `${source}::view:${idMatch[1]}`;
  }
  if (source === 'ruliweb') {
    const idMatch = String(sourceLink).match(/\/read\/(\d+)/);
    if (idMatch) return `${source}::read:${idMatch[1]}`;
  }
  return `${source}::${sourceLink}`;
}

function feedImageScore(item = {}) {
  return (item.img || item.detailImg) ? 1 : 0;
}

function shouldReplaceFeedDuplicate(prev = {}, item = {}) {
  const prevImageScore = feedImageScore(prev);
  const curImageScore = feedImageScore(item);
  if (curImageScore !== prevImageScore) return curImageScore > prevImageScore;

  const prevMs = parseDateMs(prev.updatedAt || prev.registeredAt || prev.date || '');
  const curMs = parseDateMs(item.updatedAt || item.registeredAt || item.date || '');
  return curMs >= prevMs;
}

async function readFeedItems() {
  try {
    const cutoffIso = new Date(Date.now() - FEED_LOOKBACK_HOURS * 60 * 60 * 1000).toISOString();
    const futureCutoffIso = new Date(Date.now() + FEED_FUTURE_SKEW_MINUTES * 60 * 1000).toISOString();
    const sourceFilter = FEED_SOURCES.map((source) => encodeURIComponent(source)).join(',');
    const rows = await supabaseRequest(
      `deals?source=in.(${sourceFilter})&deleted_at=is.null&registered_at=gte.${encodeURIComponent(cutoffIso)}&registered_at=lte.${encodeURIComponent(futureCutoffIso)}&select=*&order=registered_at.desc&limit=${FEED_SOURCE_LIMIT}`
    );
    const normalized = (rows || [])
      .map(normalizeFeedDbRow)
      .filter((item) => item.sourceLink && isFeedTimestampInWindow(item));
    if (normalized.length) {
      const dedupMap = new Map();
      for (const item of normalized) {
        const key = canonicalFeedKey(item);
        const prev = dedupMap.get(key);
        if (!prev) {
          dedupMap.set(key, item);
          continue;
        }
        if (shouldReplaceFeedDuplicate(prev, item)) dedupMap.set(key, item);
      }
      return applyTemperatureNormalization([...dedupMap.values()]);
    }
  } catch (_) {
    // fallback to file feeds
  }
  return readFeedItemsFromFiles();
}

async function readFeedPage({ limit = 100, offset = 0, since = '' } = {}) {
  const safeLimit = Math.max(1, Math.min(Number(limit) || 100, 600));
  const safeOffset = Math.max(0, Number(offset) || 0);
  try {
    const cutoffIso = new Date(Date.now() - FEED_LOOKBACK_HOURS * 60 * 60 * 1000).toISOString();
    const futureCutoffIso = new Date(Date.now() + FEED_FUTURE_SKEW_MINUTES * 60 * 1000).toISOString();
    const sourceFilter = FEED_SOURCES.map((source) => encodeURIComponent(source)).join(',');
    const commonFilters = [
      `source=in.(${sourceFilter})`,
      'deleted_at=is.null',
      `registered_at=gte.${encodeURIComponent(cutoffIso)}`,
      `registered_at=lte.${encodeURIComponent(futureCutoffIso)}`,
    ];
    const pageFilters = [...commonFilters];
    if (since) pageFilters.push(`updated_at=gt.${encodeURIComponent(since)}`);
    const pageOrder = since ? 'updated_at.desc' : 'registered_at.desc';

    const [pageRows, scoreRows] = await Promise.all([
      supabaseRequest(
        `deals?${pageFilters.join('&')}&select=${FEED_PAGE_COLUMNS}&order=${pageOrder}&limit=${safeLimit + 1}&offset=${safeOffset}`
      ),
      supabaseRequest(
        `deals?${commonFilters.join('&')}&select=${FEED_SCORE_COLUMNS}&limit=${FEED_SOURCE_LIMIT}`
      ).catch(() => []),
    ]);

    const rows = pageRows || [];
    const consumedRows = Math.min(rows.length, safeLimit);
    const normalized = rows
      .slice(0, safeLimit)
      .map(normalizeFeedDbRow)
      .filter((item) => item.sourceLink && isFeedTimestampInWindow(item));
    const scoreItems = (scoreRows || [])
      .map(normalizeFeedScoreRow)
      .filter((item) => isFeedTimestampInWindow(item));
    const profile = buildTemperatureProfile(scoreItems.length ? scoreItems : normalized);

    return {
      items: applyTemperatureProfile(normalized, profile),
      hasMore: rows.length > safeLimit,
      nextOffset: safeOffset + consumedRows,
    };
  } catch (_) {
    const fallbackItems = readFeedItemsFromFiles();
    const sinceMs = parseDateMs(since);
    const filtered = sinceMs
      ? fallbackItems.filter((item) => parseDateMs(item.updatedAt || item.registeredAt || item.date || '') > sinceMs)
      : fallbackItems;
    const pageItems = filtered.slice(safeOffset, safeOffset + safeLimit + 1);
    return {
      items: pageItems.slice(0, safeLimit),
      hasMore: pageItems.length > safeLimit,
      nextOffset: safeOffset + Math.min(pageItems.length, safeLimit),
    };
  }
}

function normalizeUserRow(row) {
  const img = normalizeUserImageUrl(row.img || '');
  const detailImg = normalizeUserImageUrl(row.detail_img || row.img || '');
  const manualTemperature = Math.max(0, Math.min(100, Number(row.manual_temperature ?? row.temperature ?? 100) || 100));
  const base = {
    id: `user-${row.id}`,
    title: row.title || '제목 없음',
    area: row.area || '오늘의 핫딜',
    dist: row.dist || '사용자 등록',
    time: row.time || '방금 전',
    price: row.price || '0원',
    category: row.category || '디지털',
    desc: row.desc || '',
    img,
    detailImg: detailImg || img,
    sourceLink: row.source_link || '',
    buyLink: row.buy_link || '',
    likes: Number(row.likes || 0),
    dislikes: Number(row.dislikes || 0),
    views: Number(row.views || 0),
    comments: Number(row.comments || 0),
    temperature: manualTemperature,
    manualTemperature,
    commentSignalScore: Number(row.comment_signal_score || 0),
    positiveCommentSignals: Number(row.positive_comment_signals || 0),
    negativeCommentSignals: Number(row.negative_comment_signals || 0),
    date: row.date || '',
    registeredAt: row.registered_at || row.created_at || '',
    source: 'user',
    edited: Boolean(row.edited),
    updatedAt: row.updated_at || '',
  };
  return { ...applyTemperatureNormalization([base])[0], temperature: manualTemperature, manualTemperature };
}

function parseUserId(rawId = '') {
  const id = String(rawId);
  return id.startsWith('user-') ? id.slice(5) : id;
}

function supabaseConfig() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error('Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY');
  }
  return { url, key };
}

async function supabaseRequest(endpoint, options = {}) {
  const { url, key } = supabaseConfig();
  const res = await fetch(`${url}/rest/v1/${endpoint}`, {
    ...options,
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      'Content-Type': 'application/json',
      Prefer: 'return=representation',
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Supabase error(${res.status}): ${text}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

function mapPayload(body = {}) {
  const img = normalizeUserImageUrl(body.img || '');
  const detailImg = normalizeUserImageUrl(body.detailImg || body.detail_img || body.img || '');
  return {
    title: String(body.title || '').trim(),
    desc: String(body.desc || '').trim(),
    price: String(body.price || '0원').trim(),
    category: String(body.category || '디지털').trim(),
    img,
    detail_img: detailImg || img,
    buy_link: String(body.buyLink || '').trim(),
    source_link: String(body.sourceLink || body.buyLink || '').trim(),
    area: String(body.area || '오늘의 핫딜').trim(),
    dist: String(body.dist || '방금 등록').trim(),
    time: String(body.time || '방금 전').trim(),
    views: Number(body.views || 0),
    comments: Number(body.comments || 0),
    manual_temperature: Math.max(0, Math.min(100, Number(body.manualTemperature ?? body.manual_temperature ?? body.temperature ?? 100) || 100)),
    date: String(body.date || new Date().toISOString().slice(0, 10)).trim(),
    registered_at: body.registeredAt || new Date().toISOString(),
    edited: Boolean(body.edited),
  };
}

module.exports = {
  readFeedItems,
  readFeedPage,
  readFeedItemsFromFiles,
  normalizeFeedDbRow,
  normalizeUserRow,
  parseUserId,
  computeHotScore,
  buildMetricStats,
  buildTemperatureProfile,
  computeTemperatureComponents,
  applyTemperatureProfile,
  applyTemperatureNormalization,
  HOT_SCORE_CONFIG,
  TEMPERATURE_MODEL_VERSION,
  TEMPERATURE_METRICS,
  normalizeUserImageUrl,
  canonicalFeedKey,
  shouldReplaceFeedDuplicate,
  isFeedTimestampInWindow,
  supabaseRequest,
  mapPayload,
};
