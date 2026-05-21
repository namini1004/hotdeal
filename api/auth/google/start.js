const { OAUTH_STATE_COOKIE, ensureProviderReady, getBaseUrl, randomState, redirect, setCookie } = require('../../_lib/auth');

module.exports = async (req, res) => {
  try {
    ensureProviderReady('google');
    const baseUrl = getBaseUrl(req);
    const state = randomState('google');
    setCookie(req, res, OAUTH_STATE_COOKIE, state, 600);

    const params = new URLSearchParams({
      client_id: process.env.GOOGLE_CLIENT_ID,
      redirect_uri: `${baseUrl}/api/auth/google/callback`,
      response_type: 'code',
      scope: 'openid email profile',
      state,
      prompt: 'select_account',
    });

    return redirect(res, `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`);
  } catch (error) {
    return redirect(res, `/my-gaji.html?login_error=${encodeURIComponent(error.message)}`);
  }
};
