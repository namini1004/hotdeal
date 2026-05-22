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
  redirect,
  setCookie,
  readSession,
} = require('./_lib/auth');

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
  const baseUrl = getBaseUrl(req);
  const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      code,
      client_id: process.env.GOOGLE_CLIENT_ID,
      client_secret: process.env.GOOGLE_CLIENT_SECRET,
      redirect_uri: `${baseUrl}/api/auth`,
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

function startLogin(req, res, provider) {
  if (provider !== 'google') throw new Error('Unsupported provider');
  ensureProviderReady(provider);
  const baseUrl = getBaseUrl(req);
  const state = randomState(provider);
  setCookie(req, res, OAUTH_STATE_COOKIE, state, 600);

  if (provider === 'google') {
    const params = new URLSearchParams({
      client_id: process.env.GOOGLE_CLIENT_ID,
      redirect_uri: `${baseUrl}/api/auth`,
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
  if (!code || !state || !savedState || state !== savedState) throw new Error('Invalid OAuth state');

  if (provider !== 'google') throw new Error('Unsupported provider');
  const user = await fetchGoogleUser(req, code);

  setCookie(req, res, SESSION_COOKIE, createSession(user), 60 * 60 * 24 * 30);
  clearCookie(req, res, OAUTH_STATE_COOKIE);
  return redirect(res, '/my-gaji.html?login=success');
}

module.exports = async (req, res) => {
  const { url, action, provider } = actionFrom(req);

  try {
    if (action === 'config' && req.method === 'GET') {
      const providers = providerStatus();
      return json(res, 200, {
        providers,
        ready: providers.session && providers.google,
      });
    }

    if (action === 'me' && req.method === 'GET') {
      return json(res, 200, { user: readSession(req) });
    }

    if (action === 'logout' && req.method === 'POST') {
      clearCookie(req, res, SESSION_COOKIE);
      return json(res, 200, { ok: true });
    }

    if (action === 'start' && req.method === 'GET') {
      return startLogin(req, res, provider);
    }

    if (action === 'callback' && req.method === 'GET') {
      return finishLogin(req, res, url, provider);
    }

    res.setHeader('Allow', 'GET, POST');
    return json(res, 405, { error: 'Method not allowed' });
  } catch (error) {
    if (action === 'callback') clearCookie(req, res, OAUTH_STATE_COOKIE);
    return redirect(res, `/my-gaji.html?login_error=${encodeURIComponent(error.message)}`);
  }
};
