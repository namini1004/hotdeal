const BOARD_CATEGORY_MARKER = /^<!--gaji-category:(tips|mydeals)-->/;
const VALID_BOARD_CATEGORIES = new Set(['tips', 'mydeals']);

function normalizeBoardCategory(value) {
  return VALID_BOARD_CATEGORIES.has(String(value || '').trim()) ? String(value || '').trim() : 'tips';
}

function extractBoardBody(rawBody = '') {
  const body = String(rawBody || '');
  const match = body.match(BOARD_CATEGORY_MARKER);
  return {
    category: match?.[1] || 'tips',
    body: match ? body.slice(match[0].length).replace(/^\n+/, '') : body,
  };
}

function withBoardCategoryMarker(body, category) {
  const clean = extractBoardBody(body).body;
  return `<!--gaji-category:${normalizeBoardCategory(category)}-->\n${clean}`;
}

function normalizeBoardRow(row) {
  const extracted = extractBoardBody(row.body || '');
  return {
    id: `board-${row.id}`,
    title: row.title || '제목 없음',
    body: extracted.body,
    category: extracted.category,
    img: row.img || '',
    author: row.author || '익명',
    views: Number(row.views || 0),
    createdAt: row.created_at || '',
    updatedAt: row.updated_at || '',
  };
}

function parseBoardId(rawId = '') {
  const id = String(rawId);
  return id.startsWith('board-') ? id.slice(6) : id;
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

function mapBoardPayload(body = {}) {
  return {
    title: String(body.title || '').trim(),
    body: withBoardCategoryMarker(body.body || '', body.category),
    img: String(body.img || '').trim(),
    author: String(body.author || '익명').trim() || '익명',
  };
}

module.exports = {
  normalizeBoardRow,
  parseBoardId,
  supabaseRequest,
  mapBoardPayload,
  normalizeBoardCategory,
  withBoardCategoryMarker,
};
