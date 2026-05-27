const crypto = require('crypto');
const { json, readSession } = require('../_lib/auth');
const { firestore, firebaseDebugInfo } = require('../_lib/firebase-admin');

function normalizeTerm(term) {
  return String(term || '').trim().toLowerCase().replace(/\s+/g, ' ');
}

function makeId(termNormalized) {
  return crypto.createHash('sha1').update(termNormalized).digest('hex').slice(0, 24);
}

function makeIndexId(uid, termNormalized) {
  return crypto.createHash('sha1').update(`${uid}::${termNormalized}`).digest('hex');
}

module.exports = async (req, res) => {
  const user = readSession(req);
  if (!user || !user.provider || !user.providerId) return json(res, 401, { error: 'Unauthorized' });

  const uid = `${user.provider}:${user.providerId}`;
  const db = firestore();
  const baseRef = db.collection('users').doc(uid).collection('keywords');
  const indexRef = db.collection('keyword_subscriptions');

  try {
    if (req.method === 'GET') {
      const snap = await baseRef.where('enabled', '==', true).get();
      const items = snap.docs.map((d) => ({ id: d.id, ...d.data() }));
      const deviceSnap = await db
        .collection('users')
        .doc(uid)
        .collection('devices')
        .where('enabled', '==', true)
        .limit(1)
        .get();
      return json(res, 200, { items, hasEnabledToken: !deviceSnap.empty });
    }

    if (req.method === 'POST') {
      const term = String(req.body?.term || '').trim();
      const termNormalized = normalizeTerm(term);
      if (termNormalized.length < 2 || termNormalized.length > 20) {
        return json(res, 400, { error: 'term length must be 2~20' });
      }

      const keywordId = makeId(termNormalized);
      const enabled = req.body?.enabled !== false;
      const now = new Date();
      const batch = db.batch();

      batch.set(baseRef.doc(keywordId), {
        term,
        termNormalized,
        enabled,
        createdAt: now,
        updatedAt: now,
      }, { merge: true });

      batch.set(indexRef.doc(makeIndexId(uid, termNormalized)), {
        uid,
        term,
        termNormalized,
        enabled,
        updatedAt: now,
      }, { merge: true });

      await batch.commit();
      return json(res, 200, { ok: true, id: keywordId });
    }

    if (req.method === 'DELETE') {
      const id = String(req.query?.id || req.body?.id || '').trim();
      if (!id) return json(res, 400, { error: 'id is required' });

      const keywordSnap = await baseRef.doc(id).get();
      const termNormalized = String(keywordSnap.get('termNormalized') || '').trim();

      const batch = db.batch();
      batch.delete(baseRef.doc(id));
      if (termNormalized) {
        batch.delete(indexRef.doc(makeIndexId(uid, termNormalized)));
      }
      await batch.commit();

      return json(res, 200, { ok: true });
    }

    res.setHeader('Allow', 'GET, POST, DELETE');
    return json(res, 405, { error: 'Method not allowed' });
  } catch (error) {
    const msg = String(error?.message || 'keywords failed');
    if (msg.includes('5 NOT_FOUND')) {
      return json(res, 500, {
        error: 'Firestore DB not found. Check default DB creation or set FIREBASE_DATABASE_ID.',
        debug: firebaseDebugInfo(),
      });
    }
    return json(res, 500, { error: msg });
  }
};
