const crypto = require('crypto');
const { json } = require('../_lib/auth');
const { firestore, messaging, firebaseDebugInfo } = require('../_lib/firebase-admin');
const {
  getWebPushConfig,
  isExpiredWebPushError,
  normalizeWebPushSubscription,
  sendWebPushNotification,
} = require('../_lib/web-push');

const KEYWORD_ALERT_WINDOW_MS = 30 * 60 * 1000;
const MAX_PENDING_TITLES = 5;
const MAX_PENDING_DEAL_IDS = 30;
const DUE_DIGEST_LIMIT = 50;

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

function toMillis(value) {
  if (!value) return 0;
  if (value instanceof Date) return value.getTime();
  if (typeof value.toDate === 'function') return value.toDate().getTime();
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : 0;
}

function keywordWindowId(uid, term) {
  return crypto.createHash('sha1').update(`${uid}::${term}`).digest('hex');
}

function sortMatchedTerms(termSet) {
  return [...termSet]
    .map((term) => String(term || '').trim())
    .filter(Boolean)
    .sort((a, b) => b.length - a.length || a.localeCompare(b, 'ko'));
}

function appendLimitedUnique(values, value, max) {
  const out = Array.isArray(values) ? values.filter(Boolean).map(String) : [];
  const next = String(value || '').trim();
  if (next && !out.includes(next)) out.push(next);
  return out.slice(-max);
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

function buildKeywordDigestPayload({ term, count }) {
  const safeTerm = String(term || '').trim();
  const safeCount = Math.max(1, Number(count || 0));
  return {
    title: safeTerm ? `🍆 키워드알림: ${safeTerm}` : '🍆 키워드알림',
    body: safeTerm
      ? `${safeTerm} 관련 새 딜 ${safeCount}개가 등록됐어요.`
      : `새 딜 ${safeCount}개가 등록됐어요.`,
    url: 'https://gaji.run/',
    dealId: `keyword-digest-${keywordWindowId('digest', safeTerm).slice(0, 16)}`,
    source: 'keyword_digest',
    tag: `gaji-keyword-digest-${keywordWindowId('digest', safeTerm).slice(0, 16)}`,
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

async function loadEnabledDevices(db, deviceCache, uid) {
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
  return devicesSnap;
}

function webPushDisplayMode(doc) {
  const mode = String(doc.get('displayMode') || '').trim().toLowerCase();
  if (['standalone', 'fullscreen', 'minimal-ui'].includes(mode)) return 'standalone';
  if (mode === 'webview') return 'webview';
  return 'browser';
}

function isStandaloneWebPushDevice(doc) {
  if (!normalizeWebPushSubscription(doc.get('webPushSubscription'))) return false;
  const clientKind = String(doc.get('clientKind') || '').trim().toLowerCase();
  return clientKind === 'pwa' || webPushDisplayMode(doc) === 'standalone';
}

function splitDevices(devicesSnap) {
  const hasStandaloneWebPush = devicesSnap.docs.some(isStandaloneWebPushDevice);
  let suppressedBrowserWebPushCount = 0;

  const tokens = devicesSnap.docs
    .map((d) => String(d.get('fcmToken') || '').trim())
    .filter(Boolean);

  const webDevices = devicesSnap.docs
    .map((d) => {
      const subscription = normalizeWebPushSubscription(d.get('webPushSubscription'));
      if (!subscription) return null;
      const clientKind = String(d.get('clientKind') || '').trim().toLowerCase();
      const isBrowser = clientKind !== 'pwa' && webPushDisplayMode(d) === 'browser';
      if (hasStandaloneWebPush && isBrowser) {
        suppressedBrowserWebPushCount += 1;
        return null;
      }
      return { ref: d.ref, subscription };
    })
    .filter((d) => d && d.subscription);

  return { tokens, webDevices, suppressedBrowserWebPushCount };
}

async function sendPayloadToDevices({ msg, devicesSnap, tokens, webDevices, payload, androidBody, suppressedBrowserWebPushCount = 0 }) {
  let response = { successCount: 0, failureCount: 0, responses: [] };
  const invalidTokenRefs = [];

  if (tokens.length > 0) {
    response = await msg.sendEachForMulticast({
      tokens,
      data: {
        url: payload.url || 'https://gaji.run',
        dealId: String(payload.dealId || ''),
        source: String(payload.source || ''),
        title: String(payload.title || '가지딜 알림'),
        body: String(androidBody || payload.body || '새 딜이 등록됐어요.'),
      },
      android: { priority: 'high' },
    });

    response.responses.forEach((r, idx) => {
      const code = r.error?.code || '';
      if (code.includes('registration-token-not-registered') || code.includes('invalid-registration-token')) {
        const token = tokens[idx];
        const target = devicesSnap.docs.find((d) => d.get('fcmToken') === token);
        if (target) invalidTokenRefs.push(target.ref);
      }
    });
  }

  const webPushResult = await sendWebPushToDevices(webDevices, payload);
  return {
    tokenCount: tokens.length,
    webPushCount: webDevices.length,
    successCount: response.successCount + webPushResult.successCount,
    failureCount: response.failureCount + webPushResult.failureCount,
    fcmSuccessCount: response.successCount,
    fcmFailureCount: response.failureCount,
    webPushSuccessCount: webPushResult.successCount,
    webPushFailureCount: webPushResult.failureCount,
    webPushConfigMissing: webPushResult.configMissing,
    suppressedBrowserWebPushCount,
    invalidTokenRefs,
    expiredWebPushRefs: webPushResult.expiredRefs,
  };
}

async function planKeywordAlert(db, uid, term, rowInfo, now) {
  const ref = db.collection('keyword_alert_windows').doc(keywordWindowId(uid, term));
  const dueAt = new Date(now.getTime() + KEYWORD_ALERT_WINDOW_MS);

  return db.runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    const data = snap.exists ? (snap.data() || {}) : {};
    const windowStartedAtMs = toMillis(data.windowStartedAt);
    const expired = !windowStartedAtMs || now.getTime() - windowStartedAtMs >= KEYWORD_ALERT_WINDOW_MS;
    const pendingCount = Math.max(0, Number(data.pendingCount || 0));
    const base = {
      uid,
      term,
      termNormalized: term,
      updatedAt: now,
    };

    if (!snap.exists || expired) {
      tx.set(ref, {
        ...base,
        windowStartedAt: now,
        dueAt,
        pendingCount: 0,
        pendingTitles: [],
        pendingDealIds: [],
        lastImmediateAt: now,
      }, { merge: true });
      return {
        action: 'send',
        digest: pendingCount > 0 ? { count: pendingCount, titles: data.pendingTitles || [] } : null,
      };
    }

    const nextPendingCount = pendingCount + 1;
    tx.set(ref, {
      ...base,
      dueAt: data.dueAt || dueAt,
      pendingCount: nextPendingCount,
      pendingTitles: appendLimitedUnique(data.pendingTitles, rowInfo.title, MAX_PENDING_TITLES),
      pendingDealIds: appendLimitedUnique(data.pendingDealIds, rowInfo.dealId, MAX_PENDING_DEAL_IDS),
      lastQueuedAt: now,
    }, { merge: true });

    return {
      action: 'queue',
      pendingCount: nextPendingCount,
    };
  });
}

async function flushDueKeywordDigests(db, msg, deviceCache, now) {
  let pushed = 0;
  let digests = 0;
  const snap = await db
    .collection('keyword_alert_windows')
    .where('dueAt', '<=', now)
    .limit(DUE_DIGEST_LIMIT)
    .get();

  for (const doc of snap.docs) {
    const data = doc.data() || {};
    const pendingCount = Math.max(0, Number(data.pendingCount || 0));
    const uid = String(data.uid || '').trim();
    const term = String(data.term || data.termNormalized || '').trim();
    if (!uid || !term || pendingCount <= 0) {
      await doc.ref.delete();
      continue;
    }

    const devicesSnap = await loadEnabledDevices(db, deviceCache, uid);
    const { tokens, webDevices, suppressedBrowserWebPushCount } = splitDevices(devicesSnap);
    const batch = db.batch();

    if (tokens.length === 0 && webDevices.length === 0) {
      batch.set(doc.ref, {
        pendingCount: 0,
        pendingTitles: [],
        pendingDealIds: [],
        lastDigestSkippedAt: now,
        lastDigestSkipReason: 'no_tokens',
        updatedAt: now,
      }, { merge: true });
      await batch.commit();
      continue;
    }

    const payload = buildKeywordDigestPayload({ term, count: pendingCount });
    const result = await sendPayloadToDevices({
      msg,
      devicesSnap,
      tokens,
      webDevices,
      payload,
      androidBody: payload.body,
      suppressedBrowserWebPushCount,
    });

    result.invalidTokenRefs.forEach((ref) => batch.delete(ref));
    result.expiredWebPushRefs.forEach((ref) => batch.delete(ref));
    batch.set(doc.ref, {
      pendingCount: 0,
      pendingTitles: [],
      pendingDealIds: [],
      windowStartedAt: now,
      dueAt: new Date(now.getTime() + KEYWORD_ALERT_WINDOW_MS),
      lastDigestSentAt: now,
      lastDigestCount: pendingCount,
      updatedAt: now,
    }, { merge: true });
    await batch.commit();

    pushed += result.successCount;
    digests += 1;
  }

  return { pushed, digests };
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
  let queued = 0;
  let digests = 0;

  const flushed = await flushDueKeywordDigests(db, msg, deviceCache, now);
  pushed += flushed.pushed;
  digests += flushed.digests;

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

      const devicesSnap = await loadEnabledDevices(db, deviceCache, uid);
      const { tokens, webDevices, suppressedBrowserWebPushCount } = splitDevices(devicesSnap);
      const matchedTerms = sortMatchedTerms(termSet);
      const primaryTerm = matchedTerms[0] || '';
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
      const alertPlan = await planKeywordAlert(db, uid, primaryTerm, { dealId, title, clickUrl }, now);

      if (alertPlan.action === 'queue') {
        await matchRef.set({
          dealId,
          uid,
          matchedTerms,
          status: 'queued',
          reason: 'keyword_throttle',
          throttleTerm: primaryTerm,
          queuedAt: now,
          pendingCount: alertPlan.pendingCount,
          clickUrl,
        });
        queued += 1;
        continue;
      }

      const batch = db.batch();
      const cleanupRefs = new Map();
      let digestResult = null;
      if (alertPlan.digest?.count > 0) {
        const digestPayload = buildKeywordDigestPayload({ term: primaryTerm, count: alertPlan.digest.count });
        digestResult = await sendPayloadToDevices({
          msg,
          devicesSnap,
          tokens,
          webDevices,
          payload: digestPayload,
          androidBody: digestPayload.body,
          suppressedBrowserWebPushCount,
        });
        digestResult.invalidTokenRefs.forEach((ref) => cleanupRefs.set(ref.path, ref));
        digestResult.expiredWebPushRefs.forEach((ref) => cleanupRefs.set(ref.path, ref));
        pushed += digestResult.successCount;
        digests += 1;
      }

      const result = await sendPayloadToDevices({
        msg,
        devicesSnap,
        tokens,
        webDevices,
        payload,
        androidBody: payload.body,
        suppressedBrowserWebPushCount,
      });

      result.invalidTokenRefs.forEach((ref) => cleanupRefs.set(ref.path, ref));
      result.expiredWebPushRefs.forEach((ref) => cleanupRefs.set(ref.path, ref));
      cleanupRefs.forEach((ref) => batch.delete(ref));

      batch.set(matchRef, {
        dealId,
        uid,
        matchedTerms,
        status: 'sent',
        sentAt: now,
        throttleTerm: primaryTerm,
        digestFlushed: Boolean(digestResult),
        digestCount: alertPlan.digest?.count || 0,
        tokenCount: result.tokenCount,
        webPushCount: result.webPushCount,
        successCount: result.successCount,
        failureCount: result.failureCount,
        fcmSuccessCount: result.fcmSuccessCount,
        fcmFailureCount: result.fcmFailureCount,
        webPushSuccessCount: result.webPushSuccessCount,
        webPushFailureCount: result.webPushFailureCount,
        webPushConfigMissing: result.webPushConfigMissing,
        suppressedBrowserWebPushCount: result.suppressedBrowserWebPushCount,
        clickUrl,
      });

      await batch.commit();
      pushed += result.successCount;
    }
  }

  return { ok: true, processed, pushed, skipped, queued, digests };
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
