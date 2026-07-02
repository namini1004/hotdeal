const crypto = require('crypto');
const webpush = require('web-push');

let configuredVapidKey = '';

function cleanEnv(value) {
  return String(value || '').trim();
}

function getWebPushConfig() {
  const publicKey = cleanEnv(process.env.WEB_PUSH_VAPID_PUBLIC_KEY);
  const privateKey = cleanEnv(process.env.WEB_PUSH_VAPID_PRIVATE_KEY);
  const subject = cleanEnv(process.env.WEB_PUSH_CONTACT || process.env.WEB_PUSH_SUBJECT || 'mailto:admin@gaji.run');
  return {
    publicKey,
    privateKey,
    subject,
    ready: Boolean(publicKey && privateKey),
  };
}

function getVapidPublicKey() {
  return getWebPushConfig().publicKey;
}

function ensureWebPushConfigured() {
  const config = getWebPushConfig();
  if (!config.ready) {
    throw new Error('Missing WEB_PUSH_VAPID_PUBLIC_KEY or WEB_PUSH_VAPID_PRIVATE_KEY');
  }

  const nextKey = `${config.subject}:${config.publicKey}:${config.privateKey}`;
  if (configuredVapidKey !== nextKey) {
    webpush.setVapidDetails(config.subject, config.publicKey, config.privateKey);
    configuredVapidKey = nextKey;
  }

  return config;
}

function normalizeWebPushSubscription(value) {
  if (!value || typeof value !== 'object') return null;

  const endpoint = cleanEnv(value.endpoint);
  const keys = value.keys && typeof value.keys === 'object' ? value.keys : {};
  const p256dh = cleanEnv(keys.p256dh || value.p256dh);
  const auth = cleanEnv(keys.auth || value.auth);

  if (!endpoint || !p256dh || !auth) return null;

  return {
    endpoint,
    expirationTime: value.expirationTime || null,
    keys: { p256dh, auth },
  };
}

function webPushEndpointHash(subscription) {
  const endpoint = String(subscription?.endpoint || '');
  return crypto.createHash('sha1').update(endpoint).digest('hex');
}

function webPushDeviceId(subscription) {
  return `web_${webPushEndpointHash(subscription).slice(0, 32)}`;
}

function isExpiredWebPushError(error) {
  const statusCode = Number(error?.statusCode || error?.status || 0);
  return statusCode === 404 || statusCode === 410;
}

async function sendWebPushNotification(subscription, payload) {
  ensureWebPushConfigured();
  return webpush.sendNotification(subscription, JSON.stringify(payload), {
    TTL: 60 * 60,
    urgency: 'high',
  });
}

module.exports = {
  getWebPushConfig,
  getVapidPublicKey,
  isExpiredWebPushError,
  normalizeWebPushSubscription,
  sendWebPushNotification,
  webPushDeviceId,
  webPushEndpointHash,
};
