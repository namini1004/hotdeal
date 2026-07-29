const crypto = require('crypto');

function normalizeDisplayMode(value) {
  const mode = String(value || '').trim().toLowerCase();
  if (['standalone', 'fullscreen', 'minimal-ui'].includes(mode)) return 'standalone';
  if (mode === 'webview') return 'webview';
  return 'browser';
}

function normalizeInstallationId(value) {
  const id = String(value || '').trim();
  if (!/^[a-zA-Z0-9_-]{16,120}$/.test(id)) return '';
  return id;
}

function timestampMillis(value) {
  if (!value) return 0;
  if (value instanceof Date) return value.getTime();
  if (typeof value.toDate === 'function') return value.toDate().getTime();
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : 0;
}

function deviceRecordFromDoc(uid, doc) {
  const fcmToken = String(doc.get('fcmToken') || '').trim();
  const endpointHash = String(doc.get('webPushEndpointHash') || '').trim();
  const subscription = doc.get('webPushSubscription') || null;
  const endpoint = String(subscription?.endpoint || '').trim();

  return {
    id: doc.ref.path,
    uid,
    ref: doc.ref,
    enabled: doc.get('enabled') === true,
    clientKind: String(doc.get('clientKind') || '').trim().toLowerCase(),
    displayMode: normalizeDisplayMode(doc.get('displayMode')),
    installationId: normalizeInstallationId(doc.get('webPushInstallationId')),
    userAgent: String(doc.get('userAgent') || '').trim().toLowerCase(),
    webPushEndpointHash: endpointHash || (endpoint
      ? crypto.createHash('sha1').update(endpoint).digest('hex')
      : ''),
    fcmTokenHash: fcmToken
      ? crypto.createHash('sha1').update(fcmToken).digest('hex')
      : '',
    hasWebPush: Boolean(endpoint),
    hasFcmToken: Boolean(fcmToken),
    lastSeenAtMs: timestampMillis(doc.get('lastSeenAt')),
    updatedAtMs: timestampMillis(doc.get('updatedAt')),
    createdAtMs: timestampMillis(doc.get('createdAt')),
  };
}

function isStandaloneWebPush(record) {
  return record.hasWebPush
    && (record.clientKind === 'pwa' || record.displayMode === 'standalone');
}

function recency(record) {
  return Math.max(record.lastSeenAtMs || 0, record.updatedAtMs || 0, record.createdAtMs || 0);
}

function newestFirst(a, b) {
  return recency(b) - recency(a) || String(b.id).localeCompare(String(a.id));
}

function addDuplicateActions(actionMap, records, reason) {
  if (records.length < 2) return;
  const sorted = [...records].sort(newestFirst);
  const keeper = sorted[0];
  for (const duplicate of sorted.slice(1)) {
    if (actionMap.has(duplicate.id)) continue;
    actionMap.set(duplicate.id, {
      id: duplicate.id,
      ref: duplicate.ref,
      uid: duplicate.uid,
      reason,
      supersededBy: keeper.id,
    });
  }
}

function groupBy(records, keyFor) {
  const groups = new Map();
  for (const record of records) {
    const key = keyFor(record);
    if (!key) continue;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  }
  return groups;
}

function planPushDeviceCleanup(records, options = {}) {
  const includeLegacyStandalone = options.includeLegacyStandalone === true;
  const includeFcmDuplicates = options.includeFcmDuplicates === true;
  const actionMap = new Map();
  const enabled = records.filter((record) => record.enabled);
  const byUser = groupBy(enabled, (record) => record.uid);

  for (const userRecords of byUser.values()) {
    const webRecords = userRecords.filter((record) => record.hasWebPush);
    const standaloneRecords = webRecords.filter(isStandaloneWebPush);

    if (standaloneRecords.length > 0) {
      for (const record of webRecords) {
        if (isStandaloneWebPush(record)) continue;
        actionMap.set(record.id, {
          id: record.id,
          ref: record.ref,
          uid: record.uid,
          reason: 'standalone_pwa_registered',
          supersededBy: [...standaloneRecords].sort(newestFirst)[0].id,
        });
      }
    }

    for (const group of groupBy(webRecords, (record) => record.webPushEndpointHash).values()) {
      addDuplicateActions(actionMap, group, 'duplicate_web_push_endpoint');
    }

    for (const group of groupBy(
      standaloneRecords,
      (record) => record.installationId && `${record.displayMode}:${record.installationId}`,
    ).values()) {
      addDuplicateActions(actionMap, group, 'duplicate_web_push_installation');
    }

    if (includeLegacyStandalone) {
      const standaloneWithAgent = standaloneRecords.filter((record) => record.userAgent);
      for (const group of groupBy(standaloneWithAgent, (record) => record.userAgent).values()) {
        const legacyRecords = group.filter((record) => !record.installationId);
        if (legacyRecords.length === 0) continue;
        const installedRecords = group.filter((record) => record.installationId);
        const keeper = [...(installedRecords.length > 0 ? installedRecords : legacyRecords)]
          .sort(newestFirst)[0];
        for (const duplicate of legacyRecords) {
          if (duplicate.id === keeper.id || actionMap.has(duplicate.id)) continue;
          actionMap.set(duplicate.id, {
            id: duplicate.id,
            ref: duplicate.ref,
            uid: duplicate.uid,
            reason: 'duplicate_legacy_pwa_user_agent',
            supersededBy: keeper.id,
          });
        }
      }
    }

    if (includeFcmDuplicates) {
      const fcmRecords = userRecords.filter((record) => record.hasFcmToken);
      for (const group of groupBy(fcmRecords, (record) => record.fcmTokenHash).values()) {
        addDuplicateActions(actionMap, group, 'duplicate_fcm_token');
      }
    }
  }

  return [...actionMap.values()];
}

module.exports = {
  deviceRecordFromDoc,
  isStandaloneWebPush,
  normalizeDisplayMode,
  normalizeInstallationId,
  planPushDeviceCleanup,
  timestampMillis,
};
