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

function cleanText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
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

function resolveFinalUrl(targetUrl, maxRedirects = 4) {
  return new Promise((resolve) => {
    const visit = (url, remain) => {
      const client = url.startsWith('https:') ? https : http;
      const req = client.get(url, {
        headers: { 'User-Agent': 'Mozilla/5.0 (compatible; HotdealBot/1.0; +https://hotdeal-omega.vercel.app)' },
        timeout: 8000,
      }, (res) => {
        const status = Number(res.statusCode || 0);
        const location = res.headers.location;
        res.resume();

        if ([301, 302, 303, 307, 308].includes(status) && location && remain > 0) {
          const next = absolutize(url, location);
          if (next) return visit(next, remain - 1);
        }
        return resolve(url);
      });

      req.on('timeout', () => {
        req.destroy();
        resolve(url);
      });
      req.on('error', () => resolve(url));
    };

    visit(targetUrl, maxRedirects);
  });
}

async function fetchJinaRendered(targetUrl) {
  const proxyUrl = `https://r.jina.ai/http://${targetUrl}`;
  const { html } = await fetchHtml(proxyUrl, 1);
  return html;
}

function extractFromJinaMarkdown(markdown) {
  const text = String(markdown || '');
  const titleMatch = text.match(/^Title:\s*(.+)$/mi);
  const title = cleanText(titleMatch ? titleMatch[1] : '');

  const imageMatch = text.match(/!\[[^\]]*\]\((https?:\/\/[^)]+)\)/i);
  const image = imageMatch ? cleanText(imageMatch[1]) : '';

  const lines = text
    .split('\n')
    .map((line) => cleanText(line))
    .filter(Boolean)
    .filter((line) => {
      const lower = line.toLowerCase();
      if (lower.startsWith('title:')) return false;
      if (lower.startsWith('url source:')) return false;
      if (lower.startsWith('warning:')) return false;
      if (lower.startsWith('markdown content:')) return false;
      if (/^!\[[^\]]*\]\(/.test(line)) return false;
      return true;
    });

  return {
    title,
    description: cleanText(lines.slice(0, 6).join(' ')),
    image,
  };
}

function isUsefulMeta({ title, description, image }) {
  const t = cleanText(title).toLowerCase();
  const d = cleanText(description).toLowerCase();
  const looksBlocked = [
    'just a moment',
    'forbidden',
    'access denied',
    '봇 확인',
    '확인 안내',
  ].some((keyword) => t.includes(keyword) || d.includes(keyword));

  if (looksBlocked) return false;
  return Boolean(cleanText(title) || cleanText(description) || cleanText(image));
}

function buildUrlOnlyMeta(targetUrl) {
  try {
    const parsed = new URL(targetUrl);
    const host = parsed.hostname.replace(/^www\./i, '');
    const goodsCode = parsed.searchParams.get('goodscode') || parsed.searchParams.get('goodsCode');

    if (/gmarket\.co\.kr$/i.test(parsed.hostname) && goodsCode) {
      return {
        title: `G마켓 상품 (${goodsCode})`,
        description: '접속 제한으로 상세 정보 추출에 실패했습니다. 링크는 정상 저장됩니다.',
        image: '',
      };
    }

    return {
      title: host,
      description: '접속 제한으로 상세 정보 추출에 실패했습니다. 링크는 정상 저장됩니다.',
      image: '',
    };
  } catch (_) {
    return { title: '', description: '', image: '' };
  }
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

  const resolvedUrl = await resolveFinalUrl(normalized);

  try {
    const { html, finalUrl } = await fetchHtml(normalized);
    const directMeta = {
      title: extractTitle(html),
      description: extractDescription(html),
      image: extractFirstImage(html, finalUrl),
    };

    if (isUsefulMeta(directMeta)) {
      return json(res, 200, {
        ok: true,
        url: finalUrl,
        ...directMeta,
        fallback: 'direct',
      });
    }

    const renderedMd = await fetchJinaRendered(finalUrl || resolvedUrl || normalized);
    const renderedMeta = extractFromJinaMarkdown(renderedMd);
    if (isUsefulMeta(renderedMeta)) {
      return json(res, 200, {
        ok: true,
        url: finalUrl,
        title: renderedMeta.title || directMeta.title,
        description: renderedMeta.description || directMeta.description,
        image: renderedMeta.image || directMeta.image,
        fallback: 'rendered',
      });
    }

    return json(res, 200, {
      ok: true,
      url: finalUrl,
      ...directMeta,
      fallback: 'direct',
    });
  } catch (error) {
    try {
      const renderedMd = await fetchJinaRendered(resolvedUrl || normalized);
      const renderedMeta = extractFromJinaMarkdown(renderedMd);
      if (isUsefulMeta(renderedMeta)) {
        return json(res, 200, {
          ok: true,
          url: resolvedUrl || normalized,
          ...renderedMeta,
          fallback: 'rendered',
        });
      }
    } catch (_) {
      // ignore fallback error and continue
    }

    if (/\((403|401|429|503)\)/.test(String(error.message || ''))) {
      const meta = buildUrlOnlyMeta(resolvedUrl || normalized);
      return json(res, 200, {
        ok: true,
        url: resolvedUrl || normalized,
        ...meta,
        fallback: 'url-only',
      });
    }

    return json(res, 500, { error: error.message || '링크 파싱 실패' });
  }
};
