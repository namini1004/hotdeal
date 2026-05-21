const { OAUTH_STATE_COOKIE, SESSION_COOKIE, clearCookie, createSession, ensureProviderReady, getBaseUrl, parseCookies, redirect, setCookie } = require('../../_lib/auth');

async function fetchGoogleUser(req, code) {
  const baseUrl = getBaseUrl(req);
  const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      code,
      client_id: process.env.GOOGLE_CLIENT_ID,
      client_secret: process.env.GOOGLE_CLIENT_SECRET,
      redirect_uri: `${baseUrl}/api/auth/google/callback`,
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

module.exports = async (req, res) => {
  try {
    ensureProviderReady('google');
    const url = new URL(req.url, getBaseUrl(req));
    const code = url.searchParams.get('code');
    const state = url.searchParams.get('state');
    const savedState = parseCookies(req)[OAUTH_STATE_COOKIE];
    if (!code || !state || !savedState || state !== savedState) throw new Error('Invalid OAuth state');

    const user = await fetchGoogleUser(req, code);
    setCookie(req, res, SESSION_COOKIE, createSession(user), 60 * 60 * 24 * 30);
    clearCookie(req, res, OAUTH_STATE_COOKIE);
    return redirect(res, '/my-gaji.html?login=success');
  } catch (error) {
    clearCookie(req, res, OAUTH_STATE_COOKIE);
    return redirect(res, `/my-gaji.html?login_error=${encodeURIComponent(error.message)}`);
  }
};
