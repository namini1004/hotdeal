const http = require('http');
const https = require('https');

function json(res, code, data) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(data));
}

function normalizeUrl(raw) {
  const value = String(raw || '').trim();
  if (!value) return '';
  if (/^https?:\/\//i.test(value)) return value;
  return `https://${value}`;
}

function decodeHtml(str) {
  return String(str || '')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ')
    .trim();
}

function extractMeta(html, key, attr = 'property') {
  const regex = new RegExp(`<meta[^>]*${attr}=["']${key}["'][^>]*content=["']([^"']+)["'][^>]*>`, 'i');
  const altRegex = new RegExp(`<meta[^>]*content=["']([^"']+)["'][^>]*${attr}=["']${key}["'][^>]*>`, 'i');
  const match = html.match(regex) || html.match(altRegex);
  return match ? decodeHtml(match[1]) : '';
}

function extractTitle(html) {
  const ogTitle = extractMeta(html, 'og:title');
  if (ogTitle) return ogTitle;
  const twitterTitle = extractMeta(html, 'twitter:title', 'name');
  if (twitterTitle) return twitterTitle;
  const match = html.match(/<title[^>]*>([^<]+)<\/title>/i);
  return match ? decodeHtml(match[1]) : '';
}

function extractDescription(html) {
  const ogDesc = extractMeta(html, 'og:description');
  if (ogDesc) return ogDesc;
  const twitterDesc = extractMeta(html, 'twitter:description', 'name');
  if (twitterDesc) return twitterDesc;
  const desc = extractMeta(html, 'description', 'name');
  return desc || '';
}

function absolutize(base, maybeUrl) {
  const value = String(maybeUrl || '').trim();
  if (!value) return '';
  try {
    return new URL(value, base).toString();
  } catch (_) {
    return '';
  }
}

function extractFirstImage(html, finalUrl) {
  const ogImage = extractMeta(html, 'og:image');
  if (ogImage) return absolutize(finalUrl, ogImage);
  const twitterImage = extractMeta(html, 'twitter:image', 'name');
  if (twitterImage) return absolutize(finalUrl, twitterImage);

  const imgMatches = [...html.matchAll(/<img[^>]*src=["']([^"']+)["'][^>]*>/gi)];
  for (const match of imgMatches) {
    const src = absolutize(finalUrl, match[1]);
    if (!src) continue;
    if (/\.svg($|\?)/i.test(src)) continue;
    return src;
  }
  return '';
}

function fetchHtml(targetUrl, maxRedirects = 3) {
  return new Promise((resolve, reject) => {
    const client = targetUrl.startsWith('https:') ? https : http;
    const req = client.get(targetUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; HotdealBot/1.0; +https://hotdeal-omega.vercel.app)',
        Accept: 'text/html,application/xhtml+xml',
      },
      timeout: 10000,
    }, (res) => {
      const status = Number(res.statusCode || 0);
      if ([301, 302, 303, 307, 308].includes(status)) {
        if (maxRedirects <= 0) {
          res.resume();
          reject(new Error('Too many redirects'));
          return;
        }
        const location = res.headers.location;
        res.resume();
        if (!location) {
          reject(new Error(`Redirect without location (${status})`));
          return;
        }
        const nextUrl = absolutize(targetUrl, location);
        if (!nextUrl || !/^https?:\/\//i.test(nextUrl)) {
          reject(new Error('Unsupported redirect target'));
          return;
        }
        fetchHtml(nextUrl, maxRedirects - 1).then(resolve).catch(reject);
        return;
      }

      if (status < 200 || status >= 300) {
        res.resume();
        reject(new Error(`Failed to fetch url (${status})`));
        return;
      }

      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        body += chunk;
        if (body.length > 1_500_000) {
          req.destroy(new Error('Response too large'));
        }
      });
      res.on('end', () => resolve({ html: body, finalUrl: targetUrl }));
    });

    req.on('timeout', () => req.destroy(new Error('Request timeout')));
    req.on('error', reject);
  });
}

module.exports = async (req, res) => {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return json(res, 405, { error: 'Method not allowed' });
  }

  const requestUrl = new URL(req.url, `https://${req.headers.host || 'localhost'}`);
  const normalized = normalizeUrl(requestUrl.searchParams.get('url'));
  if (!normalized || !/^https?:\/\//i.test(normalized)) {
    return json(res, 400, { error: '유효한 URL이 필요합니다.' });
  }

  try {
    const { html, finalUrl } = await fetchHtml(normalized);
    const title = extractTitle(html);
    const description = extractDescription(html);
    const image = extractFirstImage(html, finalUrl);

    return json(res, 200, {
      ok: true,
      url: finalUrl,
      title,
      description,
      image,
    });
  } catch (error) {
    return json(res, 500, { error: error.message || '링크 파싱 실패' });
  }
};
