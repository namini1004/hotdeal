const crypto = require('crypto');
const { json } = require('../_lib/auth');
const { firestore, messaging, firebaseDebugInfo } = require('../_lib/firebase-admin');
const {
  getWebPushConfig,
  isExpiredWebPushError,
  normalizeWebPushSubscription,
  sendWebPushNotification,
} = require('../_lib/web-push');

function normalizeText(...values) {
  return values
    .map((v) => String(v || '').toLowerCase())
    .join(' ')
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function buildDealId(row) {
  const source = String(row.source || '').trim();
  const sourceLink = String(row.source_link || row.sourceLink || '').trim();
  if (source && sourceLink) {
    return crypto.createHash('sha1').update(`${source}::${sourceLink}`).digest('hex');
  }
  return crypto.createHash('sha1').update(JSON.stringify(row)).digest('hex');
}

function buildCandidateTerms(normalized) {
  const words = String(normalized || '').split(' ').map((w) => w.trim()).filter(Boolean);
  const out = new Set();
  const maxN = 3;

  for (let i = 0; i < words.length; i += 1) {
    let phrase = '';
    for (let n = 1; n <= maxN && i + n <= words.length; n += 1) {
      phrase = phrase ? `${phrase} ${words[i + n - 1]}` : words[i + n - 1];
      if (phrase.length >= 2 && phrase.length <= 20) out.add(phrase);
    }
  }
  return [...out];
}

function chunkArray(values, size) {
  const out = [];
  for (let i = 0; i < values.length; i += size) out.push(values.slice(i, i + size));
  return out;
}

function buildClickUrl(row, rowId, buyLink, sourceLink) {
  if (rowId) return `https://gaji.run/detail.html?id=${encodeURIComponent(rowId)}`;
  const fallback = buyLink || sourceLink || '';
  if (fallback) return fallback;
  const source = String(row.source || '').trim();
  return source ? `https://gaji.run/?source=${encodeURIComponent(source)}` : 'https://gaji.run';
}

function buildNotificationPayload({ clickUrl, dealId, matchedTerms, source, title }) {
  const term = String(matchedTerms?.[0] || '').trim();
  return {
    title: term ? `🍆 키워드알림: ${term}` : '🍆 가지딜 알림',
    body: title || (term ? `${term} 관련 새 딜이 등록됐어요.` : '새 딜이 등록됐어요.'),
    url: clickUrl,
    dealId,
    source,
    tag: `gaji-deal-${dealId}`,
    icon: '/assets/pwa-icon-192.png',
    badge: '/assets/pwa-icon-192.png',
  };
}

async function sendWebPushToDevices(webDevices, payload) {
  if (webDevices.length === 0) {
    return { attempted: 0, successCount: 0, failureCount: 0, expiredRefs: [], configMissing: false };
  }

  if (!getWebPushConfig().ready) {
    return {
      attempted: webDevices.length,
      successCount: 0,
      failureCount: webDevices.length,
      expiredRefs: [],
      configMissing: true,
    };
  }

  let successCount = 0;
  let failureCount = 0;
  const expiredRefs = [];

  for (const device of webDevices) {
    try {
      await sendWebPushNotification(device.subscription, payload);
      successCount += 1;
    } catch (error) {
      failureCount += 1;
      if (isExpiredWebPushError(error)) expiredRefs.push(device.ref);
    }
  }

  return { attempted: webDevices.length, successCount, failureCount, expiredRefs, configMissing: false };
}

async function findMatchedUsers(db, normalizedText) {
  const candidateTerms = buildCandidateTerms(normalizedText);
  if (candidateTerms.length === 0) return new Map();

  const matched = new Map();
  for (const terms of chunkArray(candidateTerms, 30)) {
    const snap = await db
      .collection('keyword_subscriptions')
      .where('enabled', '==', true)
      .where('termNormalized', 'in', terms)
      .get();

    for (const doc of snap.docs) {
      const uid = String(doc.get('uid') || '').trim();
      const term = String(doc.get('termNormalized') || '').trim();
      if (!uid || !term) continue;
      if (!matched.has(uid)) matched.set(uid, new Set());
      matched.get(uid).add(term);
    }
  }

  return matched;
}

async function processRows(rows = []) {
  if (!rows.length) return { ok: true, processed: 0, pushed: 0, skipped: 0 };

  const db = firestore();
  const msg = messaging();
  const now = new Date();
  const deviceCache = new Map();
  let processed = 0;
  let pushed = 0;
  let skipped = 0;

  for (const row of rows) {
    if (row.deleted_at) continue;

    const sourceLink = String(row.source_link || row.sourceLink || '').trim();
    const buyLink = String(row.buy_link || row.buyLink || sourceLink).trim();
    const rowId = String(row.id || '').trim();
    const title = String(row.title || '').trim();
    const desc = String(row.desc || '').trim();
    const source = String(row.source || '').trim();
    const price = String(row.price || '').trim();
    const dealId = buildDealId(row);
    const normalized = normalizeText(title, desc, source, price);
    const matchedByUser = await findMatchedUsers(db, normalized);

    processed += 1;
    if (matchedByUser.size === 0) {
      skipped += 1;
      continue;
    }

    for (const [uid, termSet] of matchedByUser.entries()) {
      const dedupeId = `${dealId}_${uid}`;
      const matchRef = db.collection('deal_matches').doc(dedupeId);
      const matchSnap = await matchRef.get();
      if (matchSnap.exists) continue;

      let devicesSnap = deviceCache.get(uid);
      if (!devicesSnap) {
        devicesSnap = await db
          .collection('users')
          .doc(uid)
          .collection('devices')
          .where('enabled', '==', true)
          .get();
        deviceCache.set(uid, devicesSnap);
      }

      const tokens = devicesSnap.docs
        .map((d) => String(d.get('fcmToken') || '').trim())
        .filter(Boolean);

      const webDevices = devicesSnap.docs
        .map((d) => ({
          ref: d.ref,
          subscription: normalizeWebPushSubscription(d.get('webPushSubscription')),
        }))
        .filter((d) => d.subscription);

      const matchedTerms = [...termSet];
      if (tokens.length === 0 && webDevices.length === 0) {
        await matchRef.set({
          dealId,
          uid,
          matchedTerms,
          status: 'skipped',
          reason: 'no_tokens',
          sentAt: now,
        });
        continue;
      }

      const clickUrl = buildClickUrl(row, rowId, buyLink, sourceLink);
      const payload = buildNotificationPayload({ clickUrl, dealId, matchedTerms, source, title });
      let response = { successCount: 0, failureCount: 0, responses: [] };
      const invalidTokens = [];

      if (tokens.length > 0) {
        response = await msg.sendEachForMulticast({
          tokens,
          data: {
            url: clickUrl,
            dealId,
            source,
            title: payload.title,
            body: `${matchedTerms[0]} 관련 새 딜이 등록됐어요.`,
          },
          android: { priority: 'high' },
        });

        response.responses.forEach((r, idx) => {
          const code = r.error?.code || '';
          if (code.includes('registration-token-not-registered') || code.includes('invalid-registration-token')) {
            invalidTokens.push(tokens[idx]);
          }
        });
      }

      const webPushResult = await sendWebPushToDevices(webDevices, payload);

      const batch = db.batch();
      invalidTokens.forEach((token) => {
        const target = devicesSnap.docs.find((d) => d.get('fcmToken') === token);
        if (target) batch.delete(target.ref);
      });
      webPushResult.expiredRefs.forEach((ref) => batch.delete(ref));

      batch.set(matchRef, {
        dealId,
        uid,
        matchedTerms,
        status: 'sent',
        sentAt: now,
        tokenCount: tokens.length,
        webPushCount: webDevices.length,
        successCount: response.successCount + webPushResult.successCount,
        failureCount: response.failureCount + webPushResult.failureCount,
        fcmSuccessCount: response.successCount,
        fcmFailureCount: response.failureCount,
        webPushSuccessCount: webPushResult.successCount,
        webPushFailureCount: webPushResult.failureCount,
        webPushConfigMissing: webPushResult.configMissing,
        clickUrl,
      });

      await batch.commit();
      pushed += response.successCount + webPushResult.successCount;
    }
  }

  return { ok: true, processed, pushed, skipped };
}

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return json(res, 405, { error: 'Method not allowed' });
  }

  const secret = String(process.env.PUSH_INGEST_SECRET || '');
  const provided = String(req.headers['x-ingest-secret'] || '');
  if (!secret || provided !== secret) {
    return json(res, 401, { error: 'Unauthorized ingest' });
  }

  const rows = Array.isArray(req.body?.rows) ? req.body.rows : [];

  try {
    const result = await processRows(rows);
    return json(res, 200, result);
  } catch (error) {
    const msg = String(error?.message || 'ingest failed');
    if (msg.includes('5 NOT_FOUND')) {
      return json(res, 500, {
        error: 'Firestore DB not found. Check default DB creation or set FIREBASE_DATABASE_ID.',
        debug: firebaseDebugInfo(),
      });
    }
    return json(res, 500, { error: msg });
  }
};

module.exports.processRows = processRows;
