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
const {
  deviceRecordFromDoc,
  normalizeDisplayMode,
  normalizeInstallationId,
  planPushDeviceCleanup,
} = require('../_lib/push-device-dedupe');

function normalizeToken(value) {
  return String(value || '').trim();
}

function normalizeDeviceId(value, fallback) {
  const raw = String(value || fallback || '').trim();
  return raw.replace(/[\/#?\[\]]/g, '_').slice(0, 120);
}

async function disableSupersededPushDevices(db, uid, now) {
  const devicesRef = db.collection('users').doc(uid).collection('devices');
  const snap = await devicesRef.get();
  const records = snap.docs.map((doc) => deviceRecordFromDoc(uid, doc));
  const actions = planPushDeviceCleanup(records, {
    includeLegacyStandalone: true,
    includeFcmDuplicates: true,
  });
  const batch = db.batch();
  for (const action of actions) {
    batch.set(action.ref, {
      enabled: false,
      disabledAt: now,
      disabledReason: action.reason,
      supersededBy: action.supersededBy,
      updatedAt: now,
    }, { merge: true });
  }
  if (actions.length > 0) await batch.commit();
  return {
    disabled: actions.length,
    reasons: actions.reduce((counts, action) => {
      counts[action.reason] = (counts[action.reason] || 0) + 1;
      return counts;
    }, {}),
  };
}

async function hasEnabledStandaloneWebPushDevice(db, uid, currentDeviceId) {
  const devicesRef = db.collection('users').doc(uid).collection('devices');
  const snap = await devicesRef.get();

  return snap.docs.some((doc) => {
    if (doc.id === currentDeviceId) return false;
    if (!doc.get('enabled')) return false;
    if (!doc.get('webPushSubscription')) return false;
    const clientKind = String(doc.get('clientKind') || '').trim().toLowerCase();
    return clientKind === 'pwa' || normalizeDisplayMode(doc.get('displayMode')) === 'standalone';
  });
}

module.exports = async (req, res) => {
  if (req.method === 'GET') {
    const config = getWebPushConfig();
    return json(res, 200, {
      publicKey: getVapidPublicKey(),
      enabled: config.ready,
    });
  }

  if (req.method !== 'POST' && req.method !== 'DELETE') {
    res.setHeader('Allow', 'GET, POST, DELETE');
    return json(res, 405, { error: 'Method not allowed' });
  }

  try {
    const user = getActor(req, req.body || {}, readSession(req));
    if (!user || !user.provider || !user.providerId || user.anonymous || user.provider !== 'google') {
      return json(res, 401, { error: 'Google login required' });
    }

    const uid = `${user.provider}:${user.providerId}`;
    const db = firestore();
    const now = new Date();

    const token = normalizeToken(req.body?.fcmToken);
    const webPushSubscription = normalizeWebPushSubscription(
      req.body?.webPushSubscription || req.body?.subscription,
    );

    if (req.method === 'DELETE') {
      const targetDeviceId = webPushSubscription
        ? webPushDeviceId(webPushSubscription)
        : normalizeDeviceId(req.body?.deviceId, '');
      if (!targetDeviceId) return json(res, 400, { error: 'deviceId or webPushSubscription is required' });

      await db.collection('users').doc(uid).collection('devices').doc(targetDeviceId).set({
        enabled: false,
        disabledAt: now,
        disabledReason: 'user_disabled_web_push',
        updatedAt: now,
      }, { merge: true });

      return json(res, 200, { ok: true, uid, deviceId: targetDeviceId, disabled: true });
    }

    if (!token && !webPushSubscription) {
      return json(res, 400, { error: 'fcmToken or webPushSubscription is required' });
    }

    if (webPushSubscription && !getWebPushConfig().ready) {
      return json(res, 503, { error: 'Web Push is not configured' });
    }

    const deviceId = webPushSubscription
      ? webPushDeviceId(webPushSubscription)
      : normalizeDeviceId(req.body?.deviceId, crypto.createHash('sha1').update(token).digest('hex'));
    const platform = webPushSubscription ? 'web' : 'android';
    const displayMode = normalizeDisplayMode(req.body?.displayMode);
    const installationId = normalizeInstallationId(req.body?.installationId);
    const suppressedByStandalonePwa = webPushSubscription && displayMode === 'browser'
      ? await hasEnabledStandaloneWebPushDevice(db, uid, deviceId)
      : false;
    const enabled = req.body?.enabled !== false && !suppressedByStandalonePwa;

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
      devicePatch.displayMode = displayMode;
      devicePatch.clientKind = displayMode === 'standalone' ? 'pwa' : 'browser';
      if (installationId) devicePatch.webPushInstallationId = installationId;
      if (suppressedByStandalonePwa) {
        devicePatch.disabledAt = now;
        devicePatch.disabledReason = 'standalone_pwa_active';
      }
    }

    await db.collection('users').doc(uid).collection('devices').doc(deviceId).set(devicePatch, { merge: true });
    const cleanup = webPushSubscription
      ? await disableSupersededPushDevices(db, uid, now)
      : { disabled: 0, reasons: {} };

    return json(res, 200, {
      ok: true,
      uid,
      deviceId,
      platform,
      disabledBrowserWebPush: cleanup.reasons.standalone_pwa_registered || 0,
      disabledDuplicateDevices: cleanup.disabled,
      disabledReasons: cleanup.reasons,
      suppressedByStandalonePwa,
    });
  } catch (error) {
    return json(res, 500, { error: error.message || 'register failed' });
  }
};
