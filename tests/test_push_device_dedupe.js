const assert = require('node:assert/strict');
const test = require('node:test');
const { planPushDeviceCleanup } = require('../api/_lib/push-device-dedupe');

function record(overrides = {}) {
  return {
    id: overrides.id || `users/u/devices/${Math.random()}`,
    uid: overrides.uid || 'u',
    enabled: overrides.enabled !== false,
    clientKind: overrides.clientKind || 'pwa',
    displayMode: overrides.displayMode || 'standalone',
    installationId: overrides.installationId || '',
    userAgent: overrides.userAgent || '',
    webPushEndpointHash: overrides.webPushEndpointHash || '',
    fcmTokenHash: overrides.fcmTokenHash || '',
    hasWebPush: overrides.hasWebPush !== false,
    hasFcmToken: overrides.hasFcmToken === true,
    lastSeenAtMs: overrides.lastSeenAtMs || 0,
    updatedAtMs: overrides.updatedAtMs || 0,
    createdAtMs: overrides.createdAtMs || 0,
  };
}

test('keeps newest subscription for the same PWA installation', () => {
  const actions = planPushDeviceCleanup([
    record({ id: 'old', installationId: 'installation_123456', lastSeenAtMs: 10 }),
    record({ id: 'new', installationId: 'installation_123456', lastSeenAtMs: 20 }),
  ]);

  assert.deepEqual(actions.map(({ id, reason, supersededBy }) => ({ id, reason, supersededBy })), [{
    id: 'old',
    reason: 'duplicate_web_push_installation',
    supersededBy: 'new',
  }]);
});

test('disables browser push and legacy duplicate PWA subscriptions', () => {
  const actions = planPushDeviceCleanup([
    record({
      id: 'browser',
      clientKind: 'browser',
      displayMode: 'browser',
      userAgent: 'same-agent',
      lastSeenAtMs: 30,
    }),
    record({ id: 'old-pwa', userAgent: 'same-agent', lastSeenAtMs: 10 }),
    record({ id: 'new-pwa', userAgent: 'same-agent', lastSeenAtMs: 20 }),
  ], { includeLegacyStandalone: true });

  const reasons = Object.fromEntries(actions.map((action) => [action.id, action.reason]));
  assert.equal(reasons.browser, 'standalone_pwa_registered');
  assert.equal(reasons['old-pwa'], 'duplicate_legacy_pwa_user_agent');
  assert.equal(reasons['new-pwa'], undefined);
});

test('preserves legacy PWA subscriptions with different user agents', () => {
  const actions = planPushDeviceCleanup([
    record({ id: 'phone', userAgent: 'phone-agent', lastSeenAtMs: 10 }),
    record({ id: 'tablet', userAgent: 'tablet-agent', lastSeenAtMs: 20 }),
  ], { includeLegacyStandalone: true });

  assert.deepEqual(actions, []);
});

test('new installation id replaces the matching legacy PWA subscription', () => {
  const actions = planPushDeviceCleanup([
    record({ id: 'legacy', userAgent: 'same-agent', lastSeenAtMs: 30 }),
    record({
      id: 'identified',
      installationId: 'installation_123456',
      userAgent: 'same-agent',
      lastSeenAtMs: 20,
    }),
  ], { includeLegacyStandalone: true });

  assert.equal(actions.length, 1);
  assert.equal(actions[0].id, 'legacy');
  assert.equal(actions[0].supersededBy, 'identified');
});

test('preserves distinct identified PWA installations on the same user agent', () => {
  const actions = planPushDeviceCleanup([
    record({ id: 'phone-a', installationId: 'installation_aaaaaa', userAgent: 'same-agent' }),
    record({ id: 'phone-b', installationId: 'installation_bbbbbb', userAgent: 'same-agent' }),
  ], { includeLegacyStandalone: true });

  assert.deepEqual(actions, []);
});
