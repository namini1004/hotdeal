const { OAUTH_STATE_COOKIE, ensureProviderReady, getBaseUrl, randomState, redirect, setCookie } = require('../../_lib/auth');

module.exports = async (req, res) => {
  try {
    ensureProviderReady('kakao');
    const baseUrl = getBaseUrl(req);
    const state = randomState('kakao');
    setCookie(req, res, OAUTH_STATE_COOKIE, state, 600);

    const params = new URLSearchParams({
      client_id: process.env.KAKAO_REST_API_KEY,
      redirect_uri: `${baseUrl}/api/auth/kakao/callback`,
      response_type: 'code',
      state,
    });

    return redirect(res, `https://kauth.kakao.com/oauth/authorize?${params.toString()}`);
  } catch (error) {
    return redirect(res, `/my-gaji.html?login_error=${encodeURIComponent(error.message)}`);
  }
};
