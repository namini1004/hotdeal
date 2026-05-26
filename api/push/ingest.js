const crypto = require('crypto');
const { json } = require('../_lib/auth');
const { firestore } = require('../_lib/firebase-admin');

function normalizeText(...values) {
  return values
    .map((v) => String(v || '').toLowerCase())
    .join(' ')
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function buildDealId(row) {
  const source = String(row.source || '').trim();
  const sourceLink = String(row.source_link || row.sourceLink || '').trim();
  if (source && sourceLink) return `${source}::${sourceLink}`;
  return crypto.createHash('sha1').update(JSON.stringify(row)).digest('hex');
}

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return json(res, 405, { error: 'Method not allowed' });
  }

  const secret = String(process.env.PUSH_INGEST_SECRET || '');
  const provided = String(req.headers['x-ingest-secret'] || '');
  if (!secret || provided !== secret) {
    return json(res, 401, { error: 'Unauthorized ingest' });
  }

  const rows = Array.isArray(req.body?.rows) ? req.body.rows : [];
  if (!rows.length) return json(res, 200, { ok: true, inserted: 0 });

  try {
    const db = firestore();
    const batch = db.batch();
    const now = new Date();
    let inserted = 0;

    for (const row of rows) {
      if (row.deleted_at) continue;
      const dealId = buildDealId(row);
      const ingestId = crypto.createHash('sha1').update(`${dealId}:${row.updated_at || now.toISOString()}`).digest('hex');
      const sourceLink = String(row.source_link || row.sourceLink || '').trim();
      const buyLink = String(row.buy_link || row.buyLink || sourceLink).trim();
      const title = String(row.title || '').trim();
      const desc = String(row.desc || '').trim();
      const source = String(row.source || '').trim();
      const price = String(row.price || '').trim();

      const ref = db.collection('deals_ingest').doc(ingestId);
      batch.set(ref, {
        dealId,
        source,
        sourceLink,
        buyLink,
        title,
        desc,
        price,
        normalizedText: normalizeText(title, desc, source, price),
        createdAt: now,
      }, { merge: true });
      inserted += 1;
    }

    if (inserted > 0) await batch.commit();
    return json(res, 200, { ok: true, inserted });
  } catch (error) {
    return json(res, 500, { error: error.message || 'ingest failed' });
  }
};
