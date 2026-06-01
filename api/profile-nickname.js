const { readSession } = require('./_lib/auth');
const { getActor } = require('./_lib/anonymous');
const {
  sanitizeNickname,
  getNicknameProfile,
  saveNicknameProfile,
  assignUniqueAutoNickname,
  isNicknameTaken,
} = require('./_lib/nickname');

function json(res, code, data) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(data));
}

module.exports = async (req, res) => {
  try {
    const user = getActor(req, req.body || {}, readSession(req));
    if (!user) return json(res, 401, { error: 'identity required' });

    if (req.method === 'GET') {
      if (user.anonymous) return json(res, 200, { nickname: user.nickname || user.name || '' });
      const profile = await getNicknameProfile(user);
      return json(res, 200, { nickname: profile?.nickname || '' });
    }

    if (req.method === 'POST') {
      const mode = String(req.body?.mode || 'manual');
      if (mode === 'auto') {
        if (user.anonymous) return json(res, 200, { nickname: user.nickname || user.name || '' });
        const nickname = await assignUniqueAutoNickname(user);
        return json(res, 200, { nickname });
      }

      const nickname = sanitizeNickname(req.body?.nickname || '');
      if (!nickname) return json(res, 400, { error: 'nickname is required' });
      if (user.anonymous) return json(res, 200, { nickname });
      if (await isNicknameTaken(nickname)) {
        const mine = await getNicknameProfile(user);
        if (mine?.nickname !== nickname) {
          return json(res, 409, { error: 'nickname already taken' });
        }
      }
      const saved = await saveNicknameProfile(user, nickname);
      return json(res, 200, { nickname: saved.nickname || nickname });
    }

    res.setHeader('Allow', 'GET, POST');
    return json(res, 405, { error: 'Method not allowed' });
  } catch (error) {
    return json(res, 500, { error: error.message || 'server error' });
  }
};
