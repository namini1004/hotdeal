const { normalizeBoardRow, parseBoardId, supabaseRequest, mapBoardPayload } = require('../_lib/board');

function json(res, code, data) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(data));
}

module.exports = async (req, res) => {
  try {
    const id = req.query.id;
    if (!id) return json(res, 400, { error: 'id is required' });
    const boardId = parseBoardId(id);

    if (req.method === 'GET') {
      const rows = await supabaseRequest(`board_posts?id=eq.${encodeURIComponent(boardId)}&deleted_at=is.null&limit=1`);
      if (!rows?.length) return json(res, 404, { error: 'not found' });
      return json(res, 200, { item: normalizeBoardRow(rows[0]) });
    }

    if (req.method === 'PATCH') {
      const payload = { ...mapBoardPayload(req.body || {}), updated_at: new Date().toISOString() };
      const rows = await supabaseRequest(`board_posts?id=eq.${encodeURIComponent(boardId)}&deleted_at=is.null`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      if (!rows?.length) return json(res, 404, { error: 'not found' });
      return json(res, 200, { item: normalizeBoardRow(rows[0]) });
    }

    if (req.method === 'DELETE') {
      await supabaseRequest(`board_posts?id=eq.${encodeURIComponent(boardId)}&deleted_at=is.null`, {
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
