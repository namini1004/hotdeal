const { supabaseRequest } = require('./board');

const ADJECTIVES = ['빠른','차분한','반짝이는','용감한','웃는','든든한','섬세한','단단한','상냥한','기민한'];
const COLORS = ['보라','파랑','초록','하양','검정','은빛','노랑','주황','민트','분홍'];
const NOUNS = ['가지','고양이','펭귄','바람','별빛','구름','파도','여우','달빛','코끼리'];

function sanitizeNickname(value = '') {
  return String(value || '').trim().replace(/\s+/g, ' ').slice(0, 24);
}

function userKeyFromSession(user) {
  if (!user) return '';
  if (user.provider && user.providerId) return `${user.provider}:${user.providerId}`;
  if (user.email) return `email:${String(user.email).toLowerCase()}`;
  return '';
}

function randomFrom(list) {
  return list[Math.floor(Math.random() * list.length)];
}

function generateCandidate() {
  return `${randomFrom(ADJECTIVES)} ${randomFrom(COLORS)} ${randomFrom(NOUNS)}`;
}

async function getNicknameProfile(user) {
  const userKey = userKeyFromSession(user);
  if (!userKey) return null;
  const rows = await supabaseRequest(`user_profiles?user_key=eq.${encodeURIComponent(userKey)}&select=user_key,nickname&limit=1`);
  return rows?.[0] || null;
}

async function isNicknameTaken(nickname) {
  const rows = await supabaseRequest(`user_profiles?nickname=eq.${encodeURIComponent(nickname)}&select=user_key&limit=1`);
  return Boolean(rows?.length);
}

async function saveNicknameProfile(user, nickname) {
  const userKey = userKeyFromSession(user);
  if (!userKey) throw new Error('user key not found');
  const clean = sanitizeNickname(nickname);
  if (!clean) throw new Error('nickname is required');
  const payload = {
    user_key: userKey,
    provider: user.provider || '',
    provider_id: user.providerId || '',
    email: user.email || '',
    nickname: clean,
    updated_at: new Date().toISOString(),
  };
  const rows = await supabaseRequest('user_profiles?on_conflict=user_key', {
    method: 'POST',
    headers: { Prefer: 'resolution=merge-duplicates,return=representation' },
    body: JSON.stringify([payload]),
  });
  return rows?.[0] || payload;
}

async function assignUniqueAutoNickname(user) {
  const existing = await getNicknameProfile(user);
  const existingNickname = existing?.nickname || '';

  for (let i = 0; i < 60; i += 1) {
    const candidate = generateCandidate();
    // 중복 방지 + 현재 닉네임과 동일 후보 제외
    if (candidate === existingNickname) continue;
    if (await isNicknameTaken(candidate)) continue;
    await saveNicknameProfile(user, candidate);
    return candidate;
  }
  throw new Error('unique nickname generation failed');
}

module.exports = {
  sanitizeNickname,
  userKeyFromSession,
  getNicknameProfile,
  saveNicknameProfile,
  assignUniqueAutoNickname,
  isNicknameTaken,
};
