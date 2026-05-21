const { clearCookie, json, SESSION_COOKIE } = require('../_lib/auth');

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return json(res, 405, { error: 'Method not allowed' });
  }

  clearCookie(req, res, SESSION_COOKIE);
  return json(res, 200, { ok: true });
};
