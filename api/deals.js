const { readFeedItems, normalizeUserRow, supabaseRequest, mapPayload } = require('./_lib/deals');

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

module.exports = async (req, res) => {
  try {
    if (req.method === 'GET') {
      const feedItems = readFeedItems();
      let userItems = [];
      try {
        const rows = await supabaseRequest('deals?deleted_at=is.null&order=created_at.desc');
        userItems = (rows || []).map(normalizeUserRow);
      } catch (_) {
        userItems = [];
      }

      const items = dedupe([...userItems, ...feedItems]);
      return json(res, 200, { items });
    }

    if (req.method === 'POST') {
      const payload = mapPayload(req.body || {});
      if (!payload.title) return json(res, 400, { error: 'title is required' });
      const rows = await supabaseRequest('deals', {
        method: 'POST',
        body: JSON.stringify([{ ...payload, source: 'user' }]),
      });
      return json(res, 201, { item: normalizeUserRow(rows[0]) });
    }

    res.setHeader('Allow', 'GET, POST');
    return json(res, 405, { error: 'Method not allowed' });
  } catch (error) {
    return json(res, 500, { error: error.message || 'server error' });
  }
};
