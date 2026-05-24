const { readFeedItems, normalizeUserRow, parseUserId, supabaseRequest, mapPayload } = require('../_lib/deals');

function json(res, code, data) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(data));
}

module.exports = async (req, res) => {
  try {
    const id = req.query.id;
    if (!id) return json(res, 400, { error: 'id is required' });

    if (req.method === 'GET') {
      if (String(id).startsWith('user-')) {
        const userId = parseUserId(id);
        const rows = await supabaseRequest(`deals?id=eq.${encodeURIComponent(userId)}&deleted_at=is.null&limit=1`);
        if (!rows?.length) return json(res, 404, { error: 'not found' });
        return json(res, 200, { item: normalizeUserRow(rows[0]) });
      }

      const item = (await readFeedItems()).find((v) => String(v.id) === String(id));
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
  } catch (error) {
    return json(res, 500, { error: error.message || 'server error' });
  }
};
