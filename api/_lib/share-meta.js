const DEFAULT_ORIGIN = 'https://gaji.run';
const FALLBACK_IMAGE = `${DEFAULT_ORIGIN}/assets/gaji-eggplant.jpg`;

const SOURCE_LABELS = {
  ppomppu: '뽐딜',
  quasar: '퀘딜',
  fmkorea: '펨딜',
  ruliweb: '루딜',
  user: '가지딜',
  feed: '핫딜',
};

function stripTags(value = '') {
  return String(value || '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function escapeHtml(value = '') {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function normalizeOrigin(origin = DEFAULT_ORIGIN) {
  const raw = String(origin || DEFAULT_ORIGIN).trim().replace(/\/+$/, '');
  return raw || DEFAULT_ORIGIN;
}

function truncate(value = '', max = 110) {
  const text = String(value || '').trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1).trim()}…`;
}

function resolveImageUrl(img = '', origin = DEFAULT_ORIGIN) {
  const raw = String(img || '').trim();
  if (!raw) return FALLBACK_IMAGE;
  try {
    return new URL(raw, normalizeOrigin(origin)).toString();
  } catch (_) {
    return FALLBACK_IMAGE;
  }
}

function encodeId(id = '') {
  return encodeURIComponent(String(id || '').trim());
}

function getSourceLabel(source = '') {
  const key = String(source || '').trim();
  return SOURCE_LABELS[key] || key || '핫딜';
}

function buildShareMeta(item = {}, origin = DEFAULT_ORIGIN) {
  const base = normalizeOrigin(origin);
  const id = String(item.id || '').trim();
  const safeId = encodeId(id);
  const cleanTitle = stripTags(item.title || '가지딜');
  const price = stripTags(item.price || '').trim();
  const category = stripTags(item.category || '핫딜');
  const sourceLabel = getSourceLabel(item.source || '');
  const title = truncate(`[가지딜] ${cleanTitle}${price ? ` ${price}` : ''}`, 90);
  const descSource = stripTags(item.desc || '');
  const description = truncate(
    [category, sourceLabel, price].filter(Boolean).join(' · ') || descSource || '커뮤니티 핫딜과 특가 정보를 가지에서 확인해보세요.',
    150,
  );

  return {
    id,
    title,
    description,
    image: resolveImageUrl(item.img || '', base),
    canonicalUrl: `${base}/d/${safeId}`,
    detailUrl: `${base}/indexdetail.html?id=${safeId}`,
  };
}

function renderShareHtml(meta = {}) {
  const title = escapeHtml(meta.title || '[가지딜] 핫딜 상세');
  const description = escapeHtml(meta.description || '커뮤니티 핫딜과 특가 정보를 가지에서 확인해보세요.');
  const image = escapeHtml(meta.image || FALLBACK_IMAGE);
  const canonicalUrl = escapeHtml(meta.canonicalUrl || DEFAULT_ORIGIN);
  const detailUrl = escapeHtml(meta.detailUrl || DEFAULT_ORIGIN);
  const detailUrlJson = JSON.stringify(meta.detailUrl || DEFAULT_ORIGIN).replace(/</g, '\\u003c');

  return `<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="icon" type="image/svg+xml" href="/assets/favicon.svg" />
  <link rel="shortcut icon" href="/assets/favicon.svg" />
  <title>${title}</title>
  <meta name="description" content="${description}" />
  <link rel="canonical" href="${canonicalUrl}" />
  <meta property="og:type" content="product" />
  <meta property="og:site_name" content="가지딜" />
  <meta property="og:title" content="${title}" />
  <meta property="og:description" content="${description}" />
  <meta property="og:image" content="${image}" />
  <meta property="og:url" content="${canonicalUrl}" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="${title}" />
  <meta name="twitter:description" content="${description}" />
  <meta name="twitter:image" content="${image}" />
  <meta http-equiv="refresh" content="0;url=${detailUrl}" />
</head>
<body>
  <p><a href="${detailUrl}">가지딜 상세페이지로 이동합니다.</a></p>
  <script>window.location.replace(${detailUrlJson});</script>
</body>
</html>`;
}

module.exports = {
  buildShareMeta,
  renderShareHtml,
  escapeHtml,
  stripTags,
};
