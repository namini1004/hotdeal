const { json, providerStatus } = require('../_lib/auth');

module.exports = async (req, res) => {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return json(res, 405, { error: 'Method not allowed' });
  }

  const providers = providerStatus();
  return json(res, 200, {
    providers,
    ready: providers.session && (providers.google || providers.kakao),
  });
};
