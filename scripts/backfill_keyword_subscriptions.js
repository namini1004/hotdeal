#!/usr/bin/env node
const crypto = require('crypto');
const { firestore } = require('../api/_lib/firebase-admin');

function makeIndexId(uid, termNormalized) {
  return crypto.createHash('sha1').update(`${uid}::${termNormalized}`).digest('hex');
}

async function main() {
  const db = firestore();
  const usersSnap = await db.collection('users').get();

  let totalUsers = 0;
  let totalKeywords = 0;
  let totalWritten = 0;

  for (const userDoc of usersSnap.docs) {
    totalUsers += 1;
    const uid = userDoc.id;

    const keywordsSnap = await db
      .collection('users')
      .doc(uid)
      .collection('keywords')
      .where('enabled', '==', true)
      .get();

    const batch = db.batch();
    let inBatch = 0;

    for (const kwDoc of keywordsSnap.docs) {
      const data = kwDoc.data() || {};
      const termNormalized = String(data.termNormalized || '').trim();
      const term = String(data.term || termNormalized).trim();
      if (!termNormalized) continue;

      totalKeywords += 1;
      const ref = db.collection('keyword_subscriptions').doc(makeIndexId(uid, termNormalized));
      batch.set(ref, {
        uid,
        term,
        termNormalized,
        enabled: true,
        updatedAt: data.updatedAt || new Date(),
      }, { merge: true });
      inBatch += 1;
      totalWritten += 1;
    }

    if (inBatch > 0) await batch.commit();
  }

  console.log(`BACKFILL_OK users=${totalUsers} keywords=${totalKeywords} written=${totalWritten}`);
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
