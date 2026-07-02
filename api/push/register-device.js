const crypto = require('crypto');
const { json, readSession } = require('../_lib/auth');
const { getActor } = require('../_lib/anonymous');
const { firestore } = require('../_lib/firebase-admin');
const {
  getWebPushConfig,
  getVapidPublicKey,
  normalizeWebPushSubscription,
  webPushDeviceId,
  webPushEndpointHash,
} = require('../_lib/web-push');

function normalizeToken(value) {
  return String(value || '').trim();
}

function normalizeDeviceId(value, fallback) {
  const raw = String(value || fallback || '').trim();
  return raw.replace(/[\/#?\[\]]/g, '_').slice(0, 120);
}

module.exports = async (req, res) => {
  if (req.method === 'GET') {
    const config = getWebPushConfig();
    return json(res, 200, {
      publicKey: getVapidPublicKey(),
      enabled: config.ready,
    });
  }

  if (req.method !== 'POST') {
    res.setHeader('Allow', 'GET, POST');
    return json(res, 405, { error: 'Method not allowed' });
  }

  try {
    const user = getActor(req, req.body || {}, readSession(req));
    if (!user || !user.provider || !user.providerId || user.anonymous || user.provider !== 'google') {
      return json(res, 401, { error: 'Google login required' });
    }

    const token = normalizeToken(req.body?.fcmToken);
    const webPushSubscription = normalizeWebPushSubscription(
      req.body?.webPushSubscription || req.body?.subscription,
    );

    if (!token && !webPushSubscription) {
      return json(res, 400, { error: 'fcmToken or webPushSubscription is required' });
    }

    if (webPushSubscription && !getWebPushConfig().ready) {
      return json(res, 503, { error: 'Web Push is not configured' });
    }

    const uid = `${user.provider}:${user.providerId}`;
    const deviceId = webPushSubscription
      ? webPushDeviceId(webPushSubscription)
      : normalizeDeviceId(req.body?.deviceId, crypto.createHash('sha1').update(token).digest('hex'));
    const enabled = req.body?.enabled !== false;
    const platform = webPushSubscription ? 'web' : 'android';

    const db = firestore();
    const now = new Date();

    const userPatch = {
      updatedAt: now,
      createdAt: now,
    };
    if (token) {
      userPatch.platform = 'android';
      userPatch.hasAndroidDevice = true;
    }
    if (webPushSubscription) userPatch.hasWebPushDevice = true;

    await db.collection('users').doc(uid).set(userPatch, { merge: true });

    const devicePatch = {
      platform,
      enabled,
      lastSeenAt: now,
      updatedAt: now,
      createdAt: now,
    };

    if (token) {
      devicePatch.fcmToken = token;
      devicePatch.appVersion = String(req.body?.appVersion || '');
    }

    if (webPushSubscription) {
      devicePatch.webPushSubscription = webPushSubscription;
      devicePatch.webPushEndpointHash = webPushEndpointHash(webPushSubscription);
      devicePatch.userAgent = String(req.body?.userAgent || req.headers['user-agent'] || '').slice(0, 500);
      devicePatch.appVersion = String(req.body?.appVersion || 'pwa');
    }

    await db.collection('users').doc(uid).collection('devices').doc(deviceId).set(devicePatch, { merge: true });

    return json(res, 200, { ok: true, uid, deviceId, platform });
  } catch (error) {
    return json(res, 500, { error: error.message || 'register failed' });
  }
};
