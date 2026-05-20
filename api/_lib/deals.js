const fs = require('fs');
const path = require('path');

const FEED_FILES = [
  path.join(process.cwd(), 'assets', 'ppomppu_hotdeals_2days.json'),
  path.join(process.cwd(), 'assets', 'quasar_hotdeals_2days.json'),
];

function normalizeFeedItems(items = []) {
  return items.map((item, idx) => ({
    id: String(item.id ?? idx + 1),
    title: item.title || '제목 없음',
    area: item.area || '뽐뿌 핫딜',
    dist: item.dist || '기타',
    time: item.time || item.date || '',
    price: item.price || '가격 정보 확인',
    category: item.category || '기타',
    desc: item.desc || '',
    img: item.img || '',
    sourceLink: item.sourceLink || '',
    buyLink: item.buyLink || '',
    views: Number(item.views || 0),
    comments: Number(item.comments || 0),
    date: item.date || '',
    registeredAt: item.registeredAt || '',
    source: item.source || 'feed',
    edited: Boolean(item.edited),
  }));
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
  return merged;
}

function normalizeUserRow(row) {
  return {
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
    views: Number(row.views || 0),
    comments: Number(row.comments || 0),
    date: row.date || '',
    registeredAt: row.registered_at || row.created_at || '',
    source: 'user',
    edited: Boolean(row.edited),
    updatedAt: row.updated_at || '',
  };
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
