const { OAUTH_STATE_COOKIE, SESSION_COOKIE, clearCookie, createSession, ensureProviderReady, getBaseUrl, parseCookies, redirect, setCookie } = require('../../_lib/auth');

async function fetchKakaoUser(req, code) {
  const baseUrl = getBaseUrl(req);
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: process.env.KAKAO_REST_API_KEY,
    redirect_uri: `${baseUrl}/api/auth/kakao/callback`,
    code,
  });
  if (process.env.KAKAO_CLIENT_SECRET) body.set('client_secret', process.env.KAKAO_CLIENT_SECRET);

  const tokenRes = await fetch('https://kauth.kakao.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!tokenRes.ok) throw new Error(`Kakao token failed: ${tokenRes.status}`);
  const token = await tokenRes.json();

  const userRes = await fetch('https://kapi.kakao.com/v2/user/me', {
    headers: { Authorization: `Bearer ${token.access_token}` },
  });
  if (!userRes.ok) throw new Error(`Kakao profile failed: ${userRes.status}`);
  const profile = await userRes.json();
  const account = profile.kakao_account || {};
  const kakaoProfile = account.profile || {};

  return {
    provider: 'kakao',
    providerId: String(profile.id || ''),
    email: account.email || '',
    name: kakaoProfile.nickname || account.email || 'Kakao user',
    avatar: kakaoProfile.profile_image_url || kakaoProfile.thumbnail_image_url || '',
  };
}

module.exports = async (req, res) => {
  try {
    ensureProviderReady('kakao');
    const url = new URL(req.url, getBaseUrl(req));
    const code = url.searchParams.get('code');
    const state = url.searchParams.get('state');
    const savedState = parseCookies(req)[OAUTH_STATE_COOKIE];
    if (!code || !state || !savedState || state !== savedState) throw new Error('Invalid OAuth state');

    const user = await fetchKakaoUser(req, code);
    setCookie(req, res, SESSION_COOKIE, createSession(user), 60 * 60 * 24 * 30);
    clearCookie(req, res, OAUTH_STATE_COOKIE);
    return redirect(res, '/my-gaji.html?login=success');
  } catch (error) {
    clearCookie(req, res, OAUTH_STATE_COOKIE);
    return redirect(res, `/my-gaji.html?login_error=${encodeURIComponent(error.message)}`);
  }
};
