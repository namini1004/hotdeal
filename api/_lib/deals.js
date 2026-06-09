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

const HOT_SCORE_CONFIG = {
  commentWeight: 1.8,
  recencyWeight: 0.65,
  likeWeight: 1.2,
  dislikeWeight: 4.0,
  commentSignalWeight: 0.75,
  recencyWindowHours: 48,
  hotBoostHours: 3,
  negativeSignalCapThreshold: 3,
  negativeSignalTemperatureCap: 50,
};

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

function applyTemperatureNormalization(items = []) {
  const nowMs = Date.now();
  const bySource = new Map();

  for (const item of items) {
    const source = item.source || 'feed';
    if (!bySource.has(source)) bySource.set(source, []);
    bySource.get(source).push(item);
  }

  const avgBySource = new Map();
  for (const [source, list] of bySource.entries()) {
    const sumViews = list.reduce((acc, v) => acc + Math.max(0, Number(v.views || 0)), 0);
    const sumComments = list.reduce((acc, v) => acc + Math.max(0, Number(v.comments || 0)), 0);
    const n = Math.max(1, list.length);
    avgBySource.set(source, { views: sumViews / n, comments: sumComments / n });
  }

  const scored = items.map((item) => {
    const source = item.source || 'feed';
    const hotScore = computeHotScore(item, nowMs, avgBySource.get(source));
    return { ...item, hotScore };
  });

  const statsBySource = new Map();
  const scoreGroups = new Map();
  for (const item of scored) {
    const source = item.source || 'feed';
    if (!scoreGroups.has(source)) scoreGroups.set(source, []);
    scoreGroups.get(source).push(item.hotScore);
  }
  for (const [source, scores] of scoreGroups.entries()) {
    const min = Math.min(...scores);
    const max = Math.max(...scores);
    const span = max - min;
    statsBySource.set(source, { min, max, span });
  }

  return scored.map((item) => {
    const stats = statsBySource.get(item.source || 'feed') || { min: 0, span: 0 };
    let temperature = 50;
    if (stats.span > 0) {
      temperature = ((item.hotScore - stats.min) / stats.span) * 100;
    }

    let clamped = Math.max(0, Math.min(100, Math.round(temperature)));
    const isFree = String(item.price || '').trim() === '무료';
    if (isFree) {
      // 무료 딜은 0~100 정규화 결과를 80~100 구간으로 재매핑
      clamped = Math.max(80, Math.min(100, Math.round(80 + clamped * 0.2)));
    }
    if (shouldCapNegativeTemperature(item)) {
      clamped = Math.min(clamped, HOT_SCORE_CONFIG.negativeSignalTemperatureCap);
    }

    return { ...item, hotScore: Number(item.hotScore.toFixed(4)), temperature: clamped };
  });
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
  return applyTemperatureNormalization(merged);
}

function normalizeFeedDbRow(row = {}) {
  return {
    id: String(row.id || ''),
    title: row.title || '제목 없음',
    area: row.area || '뽐뿌 핫딜',
    dist: row.dist || '기타',
    time: row.time || row.date || '',
    price: inferKeywordPrice(row.title || '', row.desc || '', row.price || '') || '가격 정보 확인',
    category: row.category || '기타',
    desc: row.desc || '',
    img: row.img || '',
    detailImg: row.detail_img || row.img || '',
    sourceLink: row.source_link || '',
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

function canonicalFeedKey(item = {}) {
  const source = item.source || 'feed';
  const sourceLink = item.sourceLink || '';
  if (source === 'ppomppu') {
    const noMatch = String(sourceLink).match(/[?&]no=(\d+)/);
    if (noMatch) return `${source}::no:${noMatch[1]}`;
  }
  if (source === 'fmkorea') {
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

async function readFeedItems() {
  try {
    const batches = await Promise.all(FEED_SOURCES.map((source) =>
      supabaseRequest(
        `deals?source=eq.${encodeURIComponent(source)}&deleted_at=is.null&select=*&order=registered_at.desc&limit=${FEED_SOURCE_LIMIT}`
      ).catch(() => [])
    ));
    const rows = batches.flat();
    const normalized = (rows || []).map(normalizeFeedDbRow).filter((v) => v.sourceLink);
    if (normalized.length) {
      const dedupMap = new Map();
      for (const item of normalized) {
        const key = canonicalFeedKey(item);
        const prev = dedupMap.get(key);
        if (!prev) {
          dedupMap.set(key, item);
          continue;
        }
        const prevMs = parseDateMs(prev.updatedAt || prev.registeredAt || prev.date || '');
        const curMs = parseDateMs(item.updatedAt || item.registeredAt || item.date || '');
        if (curMs >= prevMs) dedupMap.set(key, item);
      }
      return applyTemperatureNormalization([...dedupMap.values()]);
    }
  } catch (_) {
    // fallback to file feeds
  }
  return readFeedItemsFromFiles();
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
  readFeedItemsFromFiles,
  normalizeUserRow,
  parseUserId,
  computeHotScore,
  applyTemperatureNormalization,
  canonicalFeedKey,
  supabaseRequest,
  mapPayload,
};
