const { readSession } = require('./_lib/auth');
const { getActor } = require('./_lib/anonymous');
const { normalizeBoardRow, supabaseRequest, mapBoardPayload } = require('./_lib/board');
const { getNicknameProfile } = require('./_lib/nickname');

function json(res, code, data) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(data));
}

module.exports = async (req, res) => {
  try {
    if (req.method === 'GET') {
      const rows = await supabaseRequest('board_posts?deleted_at=is.null&order=created_at.desc&limit=100');
      return json(res, 200, {
        items: (rows || []).map(normalizeBoardRow),
        serverTime: new Date().toISOString(),
      });
    }

    if (req.method === 'POST') {
      const sessionUser = getActor(req, req.body || {}, readSession(req));

      const payload = mapBoardPayload(req.body || {});
      if (!payload.title) return json(res, 400, { error: 'title is required' });
      let nickname = '';
      if (sessionUser && !sessionUser.anonymous) {
        try {
          const profile = await getNicknameProfile(sessionUser);
          nickname = profile?.nickname || '';
        } catch (_) {
          nickname = '';
        }
      }
      payload.author = nickname || sessionUser?.name || payload.author || '익명';
      const now = new Date().toISOString();
      const rows = await supabaseRequest('board_posts', {
        method: 'POST',
        body: JSON.stringify([{ ...payload, created_at: now, updated_at: now }]),
      });
      return json(res, 201, { item: normalizeBoardRow(rows[0]) });
    }

    res.setHeader('Allow', 'GET, POST');
    return json(res, 405, { error: 'Method not allowed' });
  } catch (error) {
    return json(res, 500, { error: error.message || 'server error' });
  }
};
