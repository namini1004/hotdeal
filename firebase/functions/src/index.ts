import * as admin from 'firebase-admin';
import { onDocumentCreated } from 'firebase-functions/v2/firestore';
import { logger } from 'firebase-functions';

admin.initializeApp();
const db = admin.firestore();

interface IngestDeal {
  dealId: string;
  title: string;
  desc?: string;
  source?: string;
  price?: string;
  sourceLink?: string;
  buyLink?: string;
  normalizedText?: string;
}

function normalizeText(v: string): string {
  return String(v || '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function buildCandidateTerms(normalized: string): string[] {
  const words = normalized.split(' ').map((w) => w.trim()).filter(Boolean);
  const out = new Set<string>();
  const maxN = 3;

  for (let i = 0; i < words.length; i += 1) {
    let phrase = '';
    for (let n = 1; n <= maxN && i + n <= words.length; n += 1) {
      phrase = phrase ? `${phrase} ${words[i + n - 1]}` : words[i + n - 1];
      if (phrase.length >= 2 && phrase.length <= 20) out.add(phrase);
    }
  }

  return [...out];
}

async function loadMatchedSubscriptions(candidateTerms: string[]) {
  const matches = new Map<string, Set<string>>();
  if (candidateTerms.length === 0) return matches;

  const chunks: string[][] = [];
  for (let i = 0; i < candidateTerms.length; i += 30) {
    chunks.push(candidateTerms.slice(i, i + 30));
  }

  for (const terms of chunks) {
    const snap = await db
      .collection('keyword_subscriptions')
      .where('enabled', '==', true)
      .where('termNormalized', 'in', terms)
      .get();

    for (const doc of snap.docs) {
      const uid = String(doc.get('uid') || '').trim();
      const term = String(doc.get('termNormalized') || '').trim();
      if (!uid || !term) continue;
      if (!matches.has(uid)) matches.set(uid, new Set<string>());
      matches.get(uid)!.add(term);
    }
  }

  return matches;
}

export const onDealIngestCreated = onDocumentCreated('deals_ingest/{ingestId}', async (event) => {
  const data = event.data?.data() as IngestDeal | undefined;
  if (!data?.dealId) return;

  const normalized = data.normalizedText || normalizeText(`${data.title || ''} ${data.desc || ''} ${data.source || ''} ${data.price || ''}`);
  const candidateTerms = buildCandidateTerms(normalized);
  const matchedByUser = await loadMatchedSubscriptions(candidateTerms);

  if (matchedByUser.size === 0) return;

  for (const [uid, matchedSet] of matchedByUser.entries()) {
    const matchedTerms = [...matchedSet];
    if (matchedTerms.length === 0) continue;

    const dedupeId = `${data.dealId}_${uid}`;
    const matchRef = db.collection('deal_matches').doc(dedupeId);
    const matchSnap = await matchRef.get();
    if (matchSnap.exists) continue;

    const devicesSnap = await db
      .collection('users')
      .doc(uid)
      .collection('devices')
      .where('enabled', '==', true)
      .get();

    const tokens = devicesSnap.docs
      .map((d) => String(d.get('fcmToken') || '').trim())
      .filter(Boolean);

    if (tokens.length === 0) {
      await matchRef.set({
        dealId: data.dealId,
        uid,
        matchedTerms,
        status: 'skipped',
        reason: 'no_tokens',
        sentAt: admin.firestore.FieldValue.serverTimestamp(),
      });
      continue;
    }

    const clickUrl = data.buyLink || data.sourceLink || 'https://gaji.run';
    const response = await admin.messaging().sendEachForMulticast({
      tokens,
      notification: {
        title: `🔔 관심 딜: ${matchedTerms[0]}`,
        body: data.title || '새 딜이 등록되었습니다.',
      },
      data: {
        url: clickUrl,
        dealId: data.dealId,
        source: String(data.source || ''),
      },
      android: {
        priority: 'high',
      },
    });

    const invalidTokenIndices: number[] = [];
    response.responses.forEach((r, idx) => {
      const code = r.error?.code || '';
      if (code.includes('registration-token-not-registered') || code.includes('invalid-registration-token')) {
        invalidTokenIndices.push(idx);
      }
    });

    const batch = db.batch();
    invalidTokenIndices.forEach((i) => {
      const token = tokens[i];
      const target = devicesSnap.docs.find((d) => d.get('fcmToken') === token);
      if (target) batch.delete(target.ref);
    });

    batch.set(matchRef, {
      dealId: data.dealId,
      uid,
      matchedTerms,
      status: 'sent',
      sentAt: admin.firestore.FieldValue.serverTimestamp(),
      tokenCount: tokens.length,
      successCount: response.successCount,
      failureCount: response.failureCount,
      clickUrl,
    });

    await batch.commit();
    logger.info('push sent', { dealId: data.dealId, uid, successCount: response.successCount, failureCount: response.failureCount });
  }
});
