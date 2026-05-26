const crypto = require('crypto');
const { readSession } = require('./_lib/auth');
const { readFeedItems, normalizeUserRow, supabaseRequest, mapPayload } = require('./_lib/deals');
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

module.exports = async (req, res) => {
  try {
    if (req.method === 'GET') {
      const url = new URL(req.url, 'http://localhost');
      const scope = url.searchParams.get('scope') || 'all';
      const since = url.searchParams.get('since') || '';

      const fullFeedItems = scope === 'user' ? [] : await readFeedItems();
      const feedItems = since && scope !== 'user' ? filterBySince(fullFeedItems, since) : fullFeedItems;
      let userItems = [];

      if (scope !== 'feed') {
        try {
          const query = [`deleted_at=is.null`, 'order=created_at.desc'];
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

    if (req.method === 'POST') {
      const sessionUser = readSession(req);
      if (!sessionUser) return json(res, 401, { error: 'login required' });

      const payload = mapPayload(req.body || {});
      if (!payload.title) return json(res, 400, { error: 'title is required' });
      const now = new Date().toISOString();
      const insertRow = { ...payload, source: 'user', registered_at: now, created_at: now, updated_at: now };
      const rows = await supabaseRequest('deals', {
        method: 'POST',
        body: JSON.stringify([insertRow]),
      });

      try {
        await ingestHandler.processRows([insertRow]);
      } catch (pushError) {
        // 작성 자체는 성공 처리하고, 푸시 실패 원인은 응답에 포함
        return json(res, 201, { item: normalizeUserRow(rows[0]), pushWarning: String(pushError?.message || 'push failed') });
      }

      return json(res, 201, { item: normalizeUserRow(rows[0]) });
    }

    res.setHeader('Allow', 'GET, POST');
    return json(res, 405, { error: 'Method not allowed' });
  } catch (error) {
    return json(res, 500, { error: error.message || 'server error' });
  }
};
