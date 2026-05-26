const crypto = require('crypto');
const { json, readSession } = require('../_lib/auth');
const { firestore } = require('../_lib/firebase-admin');

function normalizeToken(value) {
  return String(value || '').trim();
}

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return json(res, 405, { error: 'Method not allowed' });
  }

  try {
    const user = readSession(req);
    if (!user || !user.provider || !user.providerId) {
      return json(res, 401, { error: 'Unauthorized' });
    }

    const token = normalizeToken(req.body?.fcmToken);
    if (!token) return json(res, 400, { error: 'fcmToken is required' });

    const uid = `${user.provider}:${user.providerId}`;
    const deviceId = String(req.body?.deviceId || crypto.createHash('sha1').update(token).digest('hex'));
    const enabled = req.body?.enabled !== false;

    const db = firestore();
    const now = new Date();

    await db.collection('users').doc(uid).set({
      platform: 'android',
      updatedAt: now,
      createdAt: now,
    }, { merge: true });

    await db.collection('users').doc(uid).collection('devices').doc(deviceId).set({
      fcmToken: token,
      appVersion: String(req.body?.appVersion || ''),
      enabled,
      lastSeenAt: now,
      updatedAt: now,
      createdAt: now,
    }, { merge: true });

    return json(res, 200, { ok: true, uid, deviceId });
  } catch (error) {
    return json(res, 500, { error: error.message || 'register failed' });
  }
};
