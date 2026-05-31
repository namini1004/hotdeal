const { readFeedItems, normalizeUserRow, parseUserId, supabaseRequest } = require('./_lib/deals');
const { buildShareMeta, renderShareHtml } = require('./_lib/share-meta');

function sendHtml(res, code, html) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', 'public, max-age=300, stale-while-revalidate=3600');
  res.end(html);
}

function getOrigin(req) {
  const host = req.headers['x-forwarded-host'] || req.headers.host || 'gaji.run';
  const proto = req.headers['x-forwarded-proto'] || 'https';
  return `${proto}://${host}`;
}

async function findShareItem(id) {
  const normalizedId = parseUserId(id);

  try {
    const rows = await supabaseRequest(`deals?id=eq.${encodeURIComponent(normalizedId)}&deleted_at=is.null&limit=1`);
    if (rows?.length) {
      const row = rows[0];
      if (String(row.source || '').trim() === 'user') return normalizeUserRow(row);
      return {
        id: String(row.id || ''),
        title: row.title || '제목 없음',
        price: row.price || '가격 정보 확인',
        category: row.category || '핫딜',
        desc: row.desc || '',
        img: row.img || '',
        source: row.source || 'feed',
      };
    }
  } catch (_) {
    // 정적 feed fallback으로 계속 진행
  }

  return (await readFeedItems()).find((item) => String(item.id) === String(normalizedId)) || null;
}

module.exports = async (req, res) => {
  try {
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.setHeader('Allow', 'GET, HEAD');
      return sendHtml(res, 405, 'Method not allowed');
    }

    const id = String(req.query.id || '').trim();
    const origin = getOrigin(req);
    const item = id ? await findShareItem(id) : null;
    const meta = buildShareMeta(item || { id, title: '핫딜 상세', price: '', img: '' }, origin);
    return sendHtml(res, item ? 200 : 404, renderShareHtml(meta));
  } catch (error) {
    const origin = getOrigin(req);
    const meta = buildShareMeta({ id: String(req.query.id || ''), title: '핫딜 상세', price: '', img: '' }, origin);
    return sendHtml(res, 500, renderShareHtml(meta));
  }
};
