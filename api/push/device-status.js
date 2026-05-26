const { json, readSession } = require('../_lib/auth');
const { firestore } = require('../_lib/firebase-admin');

module.exports = async (req, res) => {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return json(res, 405, { error: 'Method not allowed' });
  }

  try {
    const user = readSession(req);
    if (!user || !user.provider || !user.providerId) {
      return json(res, 401, { error: 'Unauthorized' });
    }

    const uid = `${user.provider}:${user.providerId}`;
    const db = firestore();
    const snap = await db
      .collection('users')
      .doc(uid)
      .collection('devices')
      .where('enabled', '==', true)
      .limit(1)
      .get();

    return json(res, 200, { ok: true, hasEnabledToken: !snap.empty });
  } catch (error) {
    return json(res, 500, { error: error.message || 'device-status failed' });
  }
};
