const fs = require('fs');
const path = require('path');

const FEED_FILES = [
  path.join(process.cwd(), 'assets', 'ppomppu_hotdeals_2days.json'),
  path.join(process.cwd(), 'assets', 'quasar_hotdeals_2days.json'),
  path.join(process.cwd(), 'assets', 'fmkorea_hotdeals_2days.json'),
  path.join(process.cwd(), 'assets', 'ruliweb_hotdeals_1day.json'),
];

const HOT_SCORE_CONFIG = {
  commentWeight: 1.8,
  // 최신성은 반영하되 조회/댓글 대비 과도하게 지배하지 않도록 완화
  recencyWeight: 0.65,
  likeWeight: 0.35,
  recencyWindowHours: 48,
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

function parseDateMs(value) {
  if (!value) return 0;
  const ms = Date.parse(String(value));
  return Number.isFinite(ms) ? ms : 0;
}

function computeHotScore(item, nowMs) {
  const views = Math.max(0, Number(item.views || 0));
  const comments = Math.max(0, Number(item.comments || 0));
  const likes = Math.max(0, Number(item.likes || 0));

  const registeredMs = parseDateMs(item.registeredAt || item.date || '');
  const hoursSincePost = registeredMs
    ? Math.max(0, (nowMs - registeredMs) / (1000 * 60 * 60))
    : HOT_SCORE_CONFIG.recencyWindowHours;
  const freshness = Math.max(0, 1 - hoursSincePost / HOT_SCORE_CONFIG.recencyWindowHours);

  const viewScore = Math.log10(views + 1);
  const commentScore = Math.log10(comments + 1) * HOT_SCORE_CONFIG.commentWeight;
  const likeScore = Math.log10(likes + 1) * HOT_SCORE_CONFIG.likeWeight;
  const recencyScore = HOT_SCORE_CONFIG.recencyWeight * freshness;
  return viewScore + commentScore + likeScore + recencyScore;
}

function applyTemperatureNormalization(items = []) {
  const nowMs = Date.now();
  const bySource = new Map();
  const scored = items.map((item) => {
    const hotScore = computeHotScore(item, nowMs);
    const source = item.source || 'feed';
    if (!bySource.has(source)) bySource.set(source, []);
    bySource.get(source).push(hotScore);
    return { ...item, hotScore };
  });

  const statsBySource = new Map();
  for (const [source, scores] of bySource.entries()) {
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
    const clamped = Math.max(0, Math.min(100, Math.round(temperature)));
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
      sourceLink: item.sourceLink || '',
      buyLink: item.buyLink || '',
      likes: Number(item.likes || 0),
      views: Number(item.views || 0),
      comments: Number(item.comments || 0),
      date: item.date || '',
      registeredAt: item.registeredAt || '',
      source,
      edited: Boolean(item.edited),
    };
  });
}

function readFeedItems() {
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

function normalizeUserRow(row) {
  const base = {
    id: `user-${row.id}`,
    title: row.title || '제목 없음',
    area: row.area || '오늘의 핫딜',
    dist: row.dist || '사용자 등록',
    time: row.time || '방금 전',
    price: row.price || '0원',
    category: row.category || '디지털',
    desc: row.desc || '',
    img: row.img || '',
    sourceLink: row.source_link || '',
    buyLink: row.buy_link || '',
    likes: Number(row.likes || 0),
    views: Number(row.views || 0),
    comments: Number(row.comments || 0),
    date: row.date || '',
    registeredAt: row.registered_at || row.created_at || '',
    source: 'user',
    edited: Boolean(row.edited),
    updatedAt: row.updated_at || '',
  };
  return applyTemperatureNormalization([base])[0];
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
  return {
    title: String(body.title || '').trim(),
    desc: String(body.desc || '').trim(),
    price: String(body.price || '0원').trim(),
    category: String(body.category || '디지털').trim(),
    img: String(body.img || '').trim(),
    buy_link: String(body.buyLink || '').trim(),
    source_link: String(body.sourceLink || body.buyLink || '').trim(),
    area: String(body.area || '오늘의 핫딜').trim(),
    dist: String(body.dist || '방금 등록').trim(),
    time: String(body.time || '방금 전').trim(),
    views: Number(body.views || 0),
    comments: Number(body.comments || 0),
    date: String(body.date || new Date().toISOString().slice(0, 10)).trim(),
    registered_at: body.registeredAt || new Date().toISOString(),
    edited: Boolean(body.edited),
  };
}

module.exports = {
  readFeedItems,
  normalizeUserRow,
  parseUserId,
  supabaseRequest,
  mapPayload,
};
