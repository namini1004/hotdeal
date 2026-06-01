const crypto = require('crypto');
const { readSession } = require('./_lib/auth');
const { getActor, getActorId } = require('./_lib/anonymous');
const { readFeedItems, normalizeUserRow, parseUserId, supabaseRequest, mapPayload } = require('./_lib/deals');
const ingestHandler = require('./push/ingest');

function json(res, code, data) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(data));
}

function dedupe(items = []) {
  const seen = new Set();
  return items.filter((item) => {
    const key = item.sourceLink || `${item.id}:${item.date || ''}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function makeEtag(scope, items) {
  const fingerprint = items
    .map((v) => `${v.id}|${v.updatedAt || v.registeredAt || v.date || ''}`)
    .join('~');
  const hash = crypto.createHash('sha1').update(`${scope}:${fingerprint}`).digest('hex');
  return `W/"${hash}"`;
}

function toMs(value) {
  if (!value) return 0;
  const ms = Date.parse(String(value));
  return Number.isFinite(ms) ? ms : 0;
}

function filterBySince(items, since) {
  const sinceMs = toMs(since);
  if (!sinceMs) return items;
  return (items || []).filter((item) => {
    const candidate = item.updatedAt || item.registeredAt || item.date || '';
    return toMs(candidate) > sinceMs;
  });
}

function getSessionUserId(sessionUser) {
  return String(sessionUser?.id || sessionUser?.email || '').trim();
}

function normalizeDealKey(raw = '') {
  return String(raw || '').trim().slice(0, 512);
}

function cleanCommentString(value = '', max = 500) {
  return String(value || '').trim().slice(0, max);
}

const REPLY_MARKER_RE = /^<!--gaji-reply:([^>]+)-->\n?/;

function cleanParentCommentId(value = '') {
  return String(value || '').trim().replace(/[^a-zA-Z0-9:_-]/g, '').slice(0, 120);
}

function splitReplyBody(body = '') {
  const raw = String(body || '');
  const match = raw.match(REPLY_MARKER_RE);
  if (!match) return { parentId: '', body: raw };
  return {
    parentId: cleanParentCommentId(match[1]),
    body: raw.replace(REPLY_MARKER_RE, ''),
  };
}

function normalizeCommentRow(row = {}) {
  const parsed = splitReplyBody(row.body || row.comment || '');
  return {
    id: String(row.id || ''),
    dealKey: row.deal_key || row.dealKey || '',
    nickname: row.nickname || '익명 가지',
    body: parsed.body,
    guestKey: row.guest_key || row.guestKey || '',
    createdAt: row.created_at || row.createdAt || new Date().toISOString(),
    parentId: cleanParentCommentId(row.parent_id || row.parentId || parsed.parentId || ''),
  };
}

async function handleCommentRequest(req, res) {
  if (req.method === 'GET') {
    const dealKey = cleanCommentString(req.query?.dealKey || req.query?.deal_key || '', 800);
    if (!dealKey) return json(res, 400, { error: 'dealKey is required' });
    const rows = await supabaseRequest(`deal_comments?deal_key=eq.${encodeURIComponent(dealKey)}&select=id,deal_key,nickname,body,guest_key,created_at&order=created_at.desc&limit=100`);
    return json(res, 200, { items: (rows || []).map(normalizeCommentRow) });
  }

  if (req.method === 'POST') {
    const body = req.body || {};
    const dealKey = cleanCommentString(body.dealKey || body.deal_key || '', 800);
    const nickname = cleanCommentString(body.nickname || '', 24) || '익명 가지';
    const commentBody = cleanCommentString(body.body || body.comment || '', 500);
    const guestKey = cleanCommentString(body.guestKey || body.guest_key || '', 120);
    const parentId = cleanParentCommentId(body.parentId || body.parent_id || '');
    if (!dealKey || !commentBody) return json(res, 400, { error: 'dealKey and body are required' });

    const payload = {
      deal_key: dealKey,
      nickname,
      body: parentId ? `<!--gaji-reply:${parentId}-->\n${commentBody}` : commentBody,
      guest_key: guestKey,
      created_at: new Date().toISOString(),
    };
    const rows = await supabaseRequest('deal_comments', {
      method: 'POST',
      body: JSON.stringify([payload]),
    });
    return json(res, 201, { item: normalizeCommentRow(rows?.[0] || payload) });
  }

  res.setHeader('Allow', 'GET, POST');
  return json(res, 405, { error: 'Method not allowed' });
}

async function handleFavoriteRequest(req, res) {
  const actor = getActor(req, req.body || {}, readSession(req));
  const userId = getActorId(actor) || getSessionUserId(actor);
  if (!userId) return json(res, 401, { error: 'login required' });

  if (req.method === 'GET') {
    const rows = await supabaseRequest(
      `favorite_deals?user_id=eq.${encodeURIComponent(userId)}&select=deal_key&order=created_at.desc`,
    );
    return json(res, 200, { keys: (rows || []).map((row) => row.deal_key).filter(Boolean) });
  }

  const dealKey = normalizeDealKey(req.body?.dealKey || req.body?.deal_key || '');
  if (!dealKey) return json(res, 400, { error: 'dealKey is required' });

  if (req.method === 'POST') {
    await supabaseRequest('favorite_deals?on_conflict=user_id,deal_key', {
      method: 'POST',
      headers: { Prefer: 'resolution=merge-duplicates,return=representation' },
      body: JSON.stringify([{ user_id: userId, deal_key: dealKey }]),
    });
    return json(res, 200, { ok: true, favorited: true });
  }

  if (req.method === 'DELETE') {
    await supabaseRequest(
      `favorite_deals?user_id=eq.${encodeURIComponent(userId)}&deal_key=eq.${encodeURIComponent(dealKey)}`,
      { method: 'DELETE', headers: { Prefer: 'return=minimal' } },
    );
    return json(res, 200, { ok: true, favorited: false });
  }

  res.setHeader('Allow', 'GET, POST, DELETE');
  return json(res, 405, { error: 'Method not allowed' });
}

async function handleItemRequest(req, res, id) {
  if (!id) return json(res, 400, { error: 'id is required' });

  if (req.method === 'GET') {
    const normalizedId = parseUserId(id);

    try {
      const rows = await supabaseRequest(`deals?id=eq.${encodeURIComponent(normalizedId)}&deleted_at=is.null&limit=1`);
      if (rows?.length) {
        const row = rows[0];
        if (String(row.source || '').trim() === 'user') {
          return json(res, 200, { item: normalizeUserRow(row) });
        }
      }
    } catch (_) {
      // feed fallback로 진행
    }

    const item = (await readFeedItems()).find((v) => String(v.id) === String(normalizedId));
    if (!item) return json(res, 404, { error: 'not found' });
    return json(res, 200, { item });
  }

  if (req.method === 'PATCH') {
    const userId = parseUserId(id);
    const payload = { ...mapPayload(req.body || {}), edited: true, updated_at: new Date().toISOString() };
    const rows = await supabaseRequest(`deals?id=eq.${encodeURIComponent(userId)}&deleted_at=is.null`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    if (!rows?.length) return json(res, 404, { error: 'not found' });
    return json(res, 200, { item: normalizeUserRow(rows[0]) });
  }

  if (req.method === 'DELETE') {
    const userId = parseUserId(id);
    await supabaseRequest(`deals?id=eq.${encodeURIComponent(userId)}&deleted_at=is.null`, {
      method: 'PATCH',
      body: JSON.stringify({ deleted_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    });
    return json(res, 200, { ok: true });
  }

  res.setHeader('Allow', 'GET, PATCH, DELETE');
  return json(res, 405, { error: 'Method not allowed' });
}

module.exports = async (req, res) => {
  try {
    if (req.method === 'GET') {
      const url = new URL(req.url, 'http://localhost');
      const action = url.searchParams.get('action') || req.query?.action || '';
      if (action === 'favorites') return handleFavoriteRequest(req, res);
      if (action === 'comments') return handleCommentRequest(req, res);
      const id = url.searchParams.get('id') || req.query?.id || '';
      if (id) return handleItemRequest(req, res, id);

      const scope = url.searchParams.get('scope') || 'all';
      const since = url.searchParams.get('since') || '';

      const fullFeedItems = scope === 'user' ? [] : await readFeedItems();
      const feedItems = since && scope !== 'user' ? filterBySince(fullFeedItems, since) : fullFeedItems;
      let userItems = [];

      if (scope !== 'feed') {
        try {
          const query = [`source=eq.user`, `deleted_at=is.null`, 'order=created_at.desc'];
          if (since) query.push(`updated_at=gt.${encodeURIComponent(since)}`);
          const rows = await supabaseRequest(`deals?${query.join('&')}`);
          userItems = (rows || []).map(normalizeUserRow);
        } catch (_) {
          userItems = [];
        }
      }

      const items = dedupe([...userItems, ...feedItems]);
      const etag = makeEtag(scope, items);
      res.setHeader('Cache-Control', 'public, max-age=10, stale-while-revalidate=60');
      res.setHeader('ETag', etag);

      if (req.headers['if-none-match'] === etag) {
        res.statusCode = 304;
        return res.end();
      }

      return json(res, 200, { items, delta: Boolean(since), serverTime: new Date().toISOString() });
    }

    if (req.method === 'PATCH' || req.method === 'DELETE') {
      const url = new URL(req.url, 'http://localhost');
      const action = url.searchParams.get('action') || req.query?.action || '';
      if (action === 'favorite') return handleFavoriteRequest(req, res);
      if (action === 'comments') return handleCommentRequest(req, res);
      const id = url.searchParams.get('id') || req.query?.id || '';
      return handleItemRequest(req, res, id);
    }

    if (req.method === 'POST') {
      const url = new URL(req.url, 'http://localhost');
      const action = url.searchParams.get('action') || req.query?.action || '';
      if (action === 'favorite') return handleFavoriteRequest(req, res);
      if (action === 'comments') return handleCommentRequest(req, res);

      const actor = getActor(req, req.body || {}, readSession(req));
      if (!actor) return json(res, 401, { error: 'identity required' });

      const payload = mapPayload(req.body || {});
      if (!payload.title) return json(res, 400, { error: 'title is required' });
      const now = new Date().toISOString();
      const insertRow = { ...payload, source: 'user', registered_at: now, created_at: now, updated_at: now };
      const rows = await supabaseRequest('deals', {
        method: 'POST',
        body: JSON.stringify([insertRow]),
      });
      const createdRow = rows?.[0] || insertRow;

      try {
        await ingestHandler.processRows([createdRow]);
      } catch (pushError) {
        // 작성 자체는 성공 처리하고, 푸시 실패 원인은 응답에 포함
        return json(res, 201, { item: normalizeUserRow(createdRow), pushWarning: String(pushError?.message || 'push failed') });
      }

      return json(res, 201, { item: normalizeUserRow(createdRow) });
    }

    res.setHeader('Allow', 'GET, POST, PATCH, DELETE');
    return json(res, 405, { error: 'Method not allowed' });
  } catch (error) {
    return json(res, 500, { error: error.message || 'server error' });
  }
};
