const DEVICE_COOKIE = 'gaji_device_id';

function parseCookies(req) {
  const header = req.headers.cookie || '';
  return header.split(';').reduce((acc, part) => {
    const idx = part.indexOf('=');
    if (idx === -1) return acc;
    const key = part.slice(0, idx).trim();
    const value = part.slice(idx + 1).trim();
    if (!key) return acc;
    try {
      acc[key] = decodeURIComponent(value);
    } catch (_) {
      acc[key] = value;
    }
    return acc;
  }, {});
}

function cleanDeviceId(value = '') {
  return String(value || '').trim().replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 80);
}

function decodeMaybe(value = '') {
  try {
    return decodeURIComponent(String(value || ''));
  } catch (_) {
    return String(value || '');
  }
}

function cleanNickname(value = '') {
  return decodeMaybe(value).trim().replace(/\s+/g, ' ').slice(0, 24);
}

function getAnonymousUser(req, body = {}) {
  const cookies = parseCookies(req);
  const deviceId = cleanDeviceId(
    req.headers['x-gaji-device-id']
      || body.deviceId
      || body.device_id
      || cookies[DEVICE_COOKIE]
      || '',
  );
  if (!deviceId) return null;
  const nickname = cleanNickname(
    req.headers['x-gaji-nickname']
      || body.nickname
      || body.author
      || `가지 ${deviceId.slice(-4)}`,
  );
  return {
    id: `anon:${deviceId}`,
    provider: 'anonymous',
    providerId: deviceId,
    name: nickname,
    nickname,
    email: '',
    anonymous: true,
  };
}

function getActor(req, body = {}, sessionUser = null) {
  return sessionUser || getAnonymousUser(req, body);
}

function getActorId(actor) {
  return String(actor?.id || actor?.email || '').trim();
}

module.exports = {
  DEVICE_COOKIE,
  cleanDeviceId,
  cleanNickname,
  getAnonymousUser,
  getActor,
  getActorId,
};
