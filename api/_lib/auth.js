const crypto = require('crypto');

const SESSION_COOKIE = 'gaji_session';
const OAUTH_STATE_COOKIE = 'gaji_oauth_state';

function base64url(input) {
  return Buffer.from(input)
    .toString('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
}

function fromBase64url(input) {
  const normalized = String(input || '').replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
  return Buffer.from(padded, 'base64').toString('utf8');
}

function json(res, code, data) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(data));
}

function parseCookies(req) {
  const header = req.headers.cookie || '';
  return header.split(';').reduce((acc, part) => {
    const idx = part.indexOf('=');
    if (idx === -1) return acc;
    const key = part.slice(0, idx).trim();
    const value = part.slice(idx + 1).trim();
    if (key) {
      try {
        acc[key] = decodeURIComponent(value);
      } catch (_) {
        acc[key] = value;
      }
    }
    return acc;
  }, {});
}

function appendSetCookie(res, value) {
  const current = res.getHeader('Set-Cookie');
  if (!current) return res.setHeader('Set-Cookie', value);
  if (Array.isArray(current)) return res.setHeader('Set-Cookie', [...current, value]);
  return res.setHeader('Set-Cookie', [current, value]);
}

function cookieOptions(req, maxAge) {
  const proto = req.headers['x-forwarded-proto'] || '';
  const secure = proto === 'https' || String(req.headers.host || '').includes('vercel.app');
  return [
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    `Max-Age=${maxAge}`,
    secure ? 'Secure' : '',
  ].filter(Boolean).join('; ');
}

function setCookie(req, res, name, value, maxAge) {
  appendSetCookie(res, `${name}=${encodeURIComponent(value)}; ${cookieOptions(req, maxAge)}`);
}

function clearCookie(req, res, name) {
  setCookie(req, res, name, '', 0);
}

function getBaseUrl(req) {
  const host = req.headers['x-forwarded-host'] || req.headers.host || 'localhost';
  const proto = req.headers['x-forwarded-proto'] || (String(host).includes('localhost') ? 'http' : 'https');
  return `${proto}://${host}`;
}

function getSessionSecret() {
  const secret = process.env.AUTH_SESSION_SECRET;
  if (!secret) throw new Error('Missing AUTH_SESSION_SECRET');
  return secret;
}

function sign(data) {
  return crypto.createHmac('sha256', getSessionSecret()).update(data).digest('base64url');
}

function createSession(user) {
  const payload = {
    user,
    exp: Date.now() + 1000 * 60 * 60 * 24 * 30,
  };
  const body = base64url(JSON.stringify(payload));
  return `${body}.${sign(body)}`;
}

function readSession(req) {
  try {
    const token = parseCookies(req)[SESSION_COOKIE];
    if (!token || !token.includes('.')) return null;
    const [body, sig] = token.split('.');
    const expected = sign(body);
    if (Buffer.byteLength(sig) !== Buffer.byteLength(expected)) return null;
    if (!crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected))) return null;
    const payload = JSON.parse(fromBase64url(body));
    if (!payload.exp || payload.exp < Date.now()) return null;
    return payload.user || null;
  } catch (_) {
    return null;
  }
}

function providerStatus() {
  return {
    google: Boolean(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET),
    session: Boolean(process.env.AUTH_SESSION_SECRET),
  };
}

function ensureProviderReady(provider) {
  const status = providerStatus();
  if (!status.session) throw new Error('Missing AUTH_SESSION_SECRET');
  if (provider === 'google' && !status.google) throw new Error('Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET');
}

function signStatePayload(payload) {
  return crypto.createHmac('sha256', getSessionSecret()).update(payload).digest('base64url');
}

function randomState(provider, returnTo = '') {
  const ts = Date.now();
  const nonce = crypto.randomBytes(18).toString('hex');
  const safeReturnTo = String(returnTo || '').trim();
  const payload = safeReturnTo
    ? `${provider}:${ts}:${nonce}:${safeReturnTo}`
    : `${provider}:${ts}:${nonce}`;
  const sig = signStatePayload(payload);
  return `${payload}:${sig}`;
}

function verifyState(state, maxAgeSec = 600) {
  try {
    const parts = String(state || '').split(':');
    if (parts.length !== 4 && parts.length !== 5) return false;

    const [provider, tsRaw, nonce] = parts;
    const sig = parts[parts.length - 1];
    const returnTo = parts.length === 5 ? parts[3] : '';

    const ts = Number(tsRaw);
    if (!provider || !Number.isFinite(ts) || !nonce || !sig) return false;
    if (Math.abs(Date.now() - ts) > maxAgeSec * 1000) return false;

    const payload = returnTo
      ? `${provider}:${ts}:${nonce}:${returnTo}`
      : `${provider}:${ts}:${nonce}`;

    const expected = signStatePayload(payload);
    if (Buffer.byteLength(sig) !== Buffer.byteLength(expected)) return false;
    return crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected));
  } catch (_) {
    return false;
  }
}

function parseState(state) {
  const parts = String(state || '').split(':');
  if (parts.length === 4) {
    return { provider: parts[0] || '', returnTo: '', valid: verifyState(state) };
  }
  if (parts.length === 5) {
    return { provider: parts[0] || '', returnTo: parts[3] || '', valid: verifyState(state) };
  }
  return { provider: '', returnTo: '', valid: false };
}

function redirect(res, location) {
  res.statusCode = 302;
  res.setHeader('Location', location);
  res.end();
}

module.exports = {
  SESSION_COOKIE,
  OAUTH_STATE_COOKIE,
  json,
  parseCookies,
  setCookie,
  clearCookie,
  getBaseUrl,
  createSession,
  readSession,
  providerStatus,
  ensureProviderReady,
  randomState,
  verifyState,
  parseState,
  redirect,
};
