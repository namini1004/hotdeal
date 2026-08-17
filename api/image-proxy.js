function fail(res, code, message) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify({ error: message }));
}

module.exports = async (req, res) => {
  try {
    if (req.method !== 'GET') {
      res.setHeader('Allow', 'GET');
      return fail(res, 405, 'Method not allowed');
    }

    const url = String(req.query?.url || '').trim();
    if (!url || !/^https?:\/\//i.test(url)) {
      return fail(res, 400, 'Invalid url');
    }

    const u = new URL(url);
    const allowedHost = /(^|\.)ruliweb\.com$/i.test(u.hostname);
    if (!allowedHost) {
      return fail(res, 403, 'Host not allowed');
    }

    const upstream = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        'Referer': 'https://www.ruliweb.com/',
      },
      redirect: 'follow',
    });

    if (!upstream.ok) {
      return fail(res, upstream.status, `upstream failed (${upstream.status})`);
    }

    const contentType = upstream.headers.get('content-type') || 'application/octet-stream';
    if (!contentType.startsWith('image/')) {
      return fail(res, 502, `upstream is not image (${contentType})`);
    }

    const arrayBuf = await upstream.arrayBuffer();
    const buf = Buffer.from(arrayBuf);

    res.statusCode = 200;
    res.setHeader('Content-Type', contentType);
    res.setHeader('Cache-Control', 'public, max-age=172800, s-maxage=172800, stale-while-revalidate=86400');
    res.setHeader('Content-Length', String(buf.length));
    res.end(buf);
  } catch (e) {
    return fail(res, 500, e?.message || 'proxy failed');
  }
};
