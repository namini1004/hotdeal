const {
  OAUTH_STATE_COOKIE,
  SESSION_COOKIE,
  clearCookie,
  createSession,
  ensureProviderReady,
  getBaseUrl,
  json,
  parseCookies,
  providerStatus,
  randomState,
  parseState,
  redirect,
  setCookie,
  readSession,
} = require('./_lib/auth');
const { getNicknameProfile, assignUniqueAutoNickname } = require('./_lib/nickname');
const { getAnonymousUser } = require('./_lib/anonymous');
const handleAdmin = require('./_lib/admin');

function getGoogleRedirectUri(req) {
  const configured = (process.env.GOOGLE_REDIRECT_URI || process.env.AUTH_REDIRECT_URI || '').trim();
  return configured || `${getBaseUrl(req)}/api/auth`;
}

function normalizeReturnTo(returnTo = '') {
  const value = String(returnTo || '').trim();
  if (value === 'app') return 'app';
  if (/^[a-z0-9_-]+\.html(?:\?[a-z0-9_=&%.-]*)?$/i.test(value)) return value;
  return '';
}

function actionFrom(req) {
  const url = new URL(req.url, getBaseUrl(req));
  const stateProvider = String(url.searchParams.get('state') || '').split(':')[0];
  return {
    url,
    action: url.searchParams.get('action') || (url.searchParams.get('code') ? 'callback' : 'config'),
    provider: url.searchParams.get('provider') || stateProvider || '',
  };
}

async function fetchGoogleUser(req, code) {
  const redirectUri = getGoogleRedirectUri(req);
  const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      code,
      client_id: process.env.GOOGLE_CLIENT_ID,
      client_secret: process.env.GOOGLE_CLIENT_SECRET,
      redirect_uri: redirectUri,
      grant_type: 'authorization_code',
    }),
  });
  if (!tokenRes.ok) throw new Error(`Google token failed: ${tokenRes.status}`);
  const token = await tokenRes.json();

  const userRes = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
    headers: { Authorization: `Bearer ${token.access_token}` },
  });
  if (!userRes.ok) throw new Error(`Google profile failed: ${userRes.status}`);
  const profile = await userRes.json();

  return {
    provider: 'google',
    providerId: profile.sub,
    email: profile.email || '',
    name: profile.name || profile.email || 'Google user',
    avatar: profile.picture || '',
  };
}

function startLogin(req, res, provider, returnTo = '') {
  if (provider !== 'google') throw new Error('Unsupported provider');
  ensureProviderReady(provider);
  const redirectUri = getGoogleRedirectUri(req);
  const normalizedReturnTo = normalizeReturnTo(returnTo);
  const state = randomState(provider, normalizedReturnTo);
  setCookie(req, res, OAUTH_STATE_COOKIE, state, 600);

  if (provider === 'google') {
    const params = new URLSearchParams({
      client_id: process.env.GOOGLE_CLIENT_ID,
      redirect_uri: redirectUri,
      response_type: 'code',
      scope: 'openid email profile',
      state,
      prompt: 'select_account',
    });
    return redirect(res, `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`);
  }

  throw new Error('Unsupported provider');
}

async function finishLogin(req, res, url, provider) {
  ensureProviderReady(provider);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const savedState = parseCookies(req)[OAUTH_STATE_COOKIE];
  const stateMatchesCookie = Boolean(code && state && savedState && state === savedState);
  const parsedState = parseState(state);
  const stateSignedValid = Boolean(code && parsedState.valid);
  if (!stateMatchesCookie && !stateSignedValid) throw new Error('Invalid OAuth state');

  const returnTo = normalizeReturnTo(parsedState.returnTo);

  if (provider !== 'google') throw new Error('Unsupported provider');
  const user = await fetchGoogleUser(req, code);

  const sessionToken = createSession(user);
  setCookie(req, res, SESSION_COOKIE, sessionToken, 60 * 60 * 24 * 30);
  clearCookie(req, res, OAUTH_STATE_COOKIE);

  if (returnTo === 'app') {
    const deepLink = `gaji://auth?login=success&session=${encodeURIComponent(sessionToken)}`;
    return redirect(res, deepLink);
  }
  if (returnTo) return redirect(res, `/${returnTo}`);

  return redirect(res, '/my-gaji.html?login=success');
}

module.exports = async (req, res) => {
  const { url, action, provider } = actionFrom(req);

  try {
    if (action === 'admin') {
      return await handleAdmin(req, res);
    }

    if (action === 'config' && req.method === 'GET') {
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
      const providers = providerStatus();
      return json(res, 200, {
        providers,
        ready: providers.session && providers.google,
      });
    }

    if (action === 'me' && req.method === 'GET') {
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
      const user = readSession(req) || getAnonymousUser(req);
      if (!user) return json(res, 200, { user: null });
      let nickname = '';
      try {
        if (user.anonymous) {
          nickname = user.nickname || user.name || '';
        } else {
          const profile = await getNicknameProfile(user);
          nickname = profile?.nickname || '';
        }
        if (!nickname && !user.anonymous) {
          nickname = await assignUniqueAutoNickname(user);
        }
      } catch (_) {
        nickname = user.nickname || '';
      }
      return json(res, 200, { user: { ...user, nickname } });
    }

    if (action === 'logout' && req.method === 'POST') {
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
      clearCookie(req, res, SESSION_COOKIE);
      return json(res, 200, { ok: true });
    }

    if (action === 'start' && req.method === 'GET') {
      const returnTo = url.searchParams.get('return_to') || '';
      return startLogin(req, res, provider, returnTo);
    }

    if (action === 'callback' && req.method === 'GET') {
      return await finishLogin(req, res, url, provider);
    }

    res.setHeader('Allow', 'GET, POST');
    return json(res, 405, { error: 'Method not allowed' });
  } catch (error) {
    if (action === 'callback') clearCookie(req, res, OAUTH_STATE_COOKIE);
    return redirect(res, `/my-gaji.html?login_error=${encodeURIComponent(error.message)}`);
  }
};
