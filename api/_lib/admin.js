const { json, readSession, parseCookies, setCookie, clearCookie, createSession, SESSION_COOKIE } = require('./auth');
const { readFeedItems, normalizeUserRow, parseUserId, supabaseRequest, mapPayload } = require('./deals');
const { normalizeBoardRow, parseBoardId, mapBoardPayload } = require('./board');

const ADMIN_COOKIE = 'gaji_admin_session';
const DEFAULT_ADMIN_EMAILS = ['namini1004@gmail.com'];

function adminEmails() {
  const configured = String(process.env.ADMIN_EMAILS || '')
    .split(',')
    .map((v) => v.trim().toLowerCase())
    .filter(Boolean);
  return [...new Set([...DEFAULT_ADMIN_EMAILS, ...configured])];
}

function isConfigured() {
  return Boolean(process.env.AUTH_SESSION_SECRET && (adminEmails().length || process.env.ADMIN_PASSWORD));
}

function verifyAdminCookie(req) {
  const token = parseCookies(req)[ADMIN_COOKIE];
  if (!token) return null;
  return readSession({ headers: { cookie: `${SESSION_COOKIE}=${encodeURIComponent(token)}` } });
}

function getAdmin(req) {
  const cookieAdmin = verifyAdminCookie(req);
  if (cookieAdmin?.role === 'admin') return cookieAdmin;

  const user = readSession(req);
  const allow = adminEmails();
  const email = String(user?.email || '').toLowerCase();
  if (email && allow.includes(email)) {
    return { role: 'admin', email, name: user.name || email, provider: user.provider || 'google' };
  }
  return null;
}

function requireAdmin(req, res) {
  if (!isConfigured()) {
    json(res, 503, { error: 'admin is not configured', setupRequired: true });
    return null;
  }
  const admin = getAdmin(req);
  if (!admin) {
    json(res, 401, { error: 'admin login required' });
    return null;
  }
  return admin;
}

function value(raw = '', max = 5000) {
  return String(raw || '').trim().slice(0, max);
}

function bool(raw) {
  return raw === true || raw === 'true' || raw === 1 || raw === '1';
}

async function safeRows(endpoint, fallback = []) {
  try {
    return await supabaseRequest(endpoint);
  } catch (error) {
    return fallback;
  }
}

async function safeCount(endpoint) {
  return (await safeRows(`${endpoint}&select=id`, [])).length;
}

function normalizeCommentRow(row = {}) {
  return {
    id: String(row.id || ''),
    dealKey: row.deal_key || row.dealKey || '',
    nickname: row.nickname || '익명',
    body: row.body || '',
    guestKey: row.guest_key || '',
    createdAt: row.created_at || '',
  };
}

function normalizeUserProfile(row = {}) {
  return {
    userKey: row.user_key || '',
    provider: row.provider || '',
    email: row.email || '',
    nickname: row.nickname || '',
    status: row.status || 'active',
    role: row.role || 'user',
    memo: row.memo || '',
    updatedAt: row.updated_at || row.created_at || '',
  };
}

function normalizeReport(row = {}) {
  return {
    id: String(row.id || ''),
    targetType: row.target_type || row.targetType || 'deal',
    targetId: row.target_id || row.targetId || '',
    reason: row.reason || '',
    memo: row.memo || '',
    reporter: row.reporter || '',
    status: row.status || 'pending',
    createdAt: row.created_at || '',
    updatedAt: row.updated_at || '',
  };
}

function normalizeNotice(row = {}) {
  return {
    id: String(row.id || ''),
    title: row.title || '',
    body: row.body || '',
    pinned: Boolean(row.pinned),
    published: row.published !== false,
    startsAt: row.starts_at || '',
    endsAt: row.ends_at || '',
    createdAt: row.created_at || '',
    updatedAt: row.updated_at || '',
  };
}

function normalizeDealRow(row = {}) {
  if (String(row.source || 'user') === 'user') return normalizeUserRow(row);
  return {
    id: String(row.id || ''),
    title: row.title || '제목 없음',
    area: row.area || '',
    dist: row.dist || '',
    time: row.time || row.date || '',
    price: row.price || '',
    category: row.category || '',
    desc: row.desc || '',
    img: row.img || '',
    detailImg: row.detail_img || row.img || '',
    sourceLink: row.source_link || '',
    buyLink: row.buy_link || '',
    likes: Number(row.likes || 0),
    views: Number(row.views || 0),
    comments: Number(row.comments || 0),
    date: row.date || '',
    registeredAt: row.registered_at || row.created_at || '',
    source: row.source || 'feed',
    edited: Boolean(row.edited),
    updatedAt: row.updated_at || '',
  };
}

async function listDeals() {
  const rows = await safeRows('deals?deleted_at=is.null&order=created_at.desc&limit=200', null);
  if (Array.isArray(rows)) {
    return rows.map(normalizeDealRow);
  }
  return (await readFeedItems()).slice(0, 200);
}

async function handleDashboard(req, res) {
  const [deals, comments, boardPosts, reports, notices, users] = await Promise.all([
    listDeals(),
    safeRows('deal_comments?order=created_at.desc&limit=200', []),
    safeRows('board_posts?deleted_at=is.null&order=created_at.desc&limit=100', []),
    safeRows('admin_reports?order=created_at.desc&limit=100', []),
    safeRows('admin_notices?order=created_at.desc&limit=100', []),
    safeRows('user_profiles?order=updated_at.desc&limit=200', []),
  ]);
  const today = new Date().toISOString().slice(0, 10);
  const todayDeals = deals.filter((v) => String(v.registeredAt || v.date || '').startsWith(today)).length;
  const pendingReports = reports.filter((v) => (v.status || 'pending') === 'pending').length;
  const hotDeals = [...deals]
    .sort((a, b) => Number(b.temperature || b.views || 0) - Number(a.temperature || a.views || 0))
    .slice(0, 10);
  return json(res, 200, {
    summary: {
      totalDeals: deals.length,
      todayDeals,
      comments: comments.length,
      users: users.length,
      boardPosts: boardPosts.length,
      pendingReports,
      activeNotices: notices.filter((v) => v.published !== false).length,
    },
    hotDeals,
    recent: {
      deals: deals.slice(0, 8),
      comments: comments.slice(0, 8).map(normalizeCommentRow),
      reports: reports.slice(0, 8).map(normalizeReport),
    },
  });
}

async function handleDeals(req, res, url) {
  const id = url.searchParams.get('id') || req.query?.id || '';
  if (req.method === 'GET') return json(res, 200, { items: await listDeals() });

  if (req.method === 'POST') {
    const now = new Date().toISOString();
    const payload = { ...mapPayload(req.body || {}), source: 'user', registered_at: now, created_at: now, updated_at: now, edited: true };
    if (!payload.title) return json(res, 400, { error: 'title is required' });
    const rows = await supabaseRequest('deals', { method: 'POST', body: JSON.stringify([payload]) });
    return json(res, 201, { item: normalizeUserRow(rows?.[0] || payload) });
  }

  if (!id) return json(res, 400, { error: 'id is required' });
  const dealId = parseUserId(id);
  if (req.method === 'PATCH') {
    const payload = { ...mapPayload(req.body || {}), updated_at: new Date().toISOString(), edited: true };
    const rows = await supabaseRequest(`deals?id=eq.${encodeURIComponent(dealId)}&deleted_at=is.null`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    return json(res, 200, { item: normalizeUserRow(rows?.[0] || payload) });
  }
  if (req.method === 'DELETE') {
    await supabaseRequest(`deals?id=eq.${encodeURIComponent(dealId)}&deleted_at=is.null`, {
      method: 'PATCH',
      body: JSON.stringify({ deleted_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    });
    return json(res, 200, { ok: true });
  }
  res.setHeader('Allow', 'GET, POST, PATCH, DELETE');
  return json(res, 405, { error: 'Method not allowed' });
}

async function handleUsers(req, res, url) {
  if (req.method === 'GET') {
    const profiles = await safeRows('user_profiles?order=updated_at.desc&limit=300', []);
    return json(res, 200, { items: profiles.map(normalizeUserProfile) });
  }
  const userKey = value(req.body?.userKey || url.searchParams.get('userKey') || '', 240);
  if (!userKey) return json(res, 400, { error: 'userKey is required' });
  if (req.method === 'PATCH') {
    const payload = {
      status: value(req.body?.status || 'active', 24),
      role: value(req.body?.role || 'user', 24),
      memo: value(req.body?.memo || '', 1000),
      updated_at: new Date().toISOString(),
    };
    const rows = await supabaseRequest(`user_profiles?user_key=eq.${encodeURIComponent(userKey)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    return json(res, 200, { item: normalizeUserProfile(rows?.[0] || { user_key: userKey, ...payload }) });
  }
  res.setHeader('Allow', 'GET, PATCH');
  return json(res, 405, { error: 'Method not allowed' });
}

async function handleComments(req, res, url) {
  const id = value(req.body?.id || url.searchParams.get('id') || '', 120);
  if (req.method === 'GET') {
    const rows = await safeRows('deal_comments?order=created_at.desc&limit=300', []);
    return json(res, 200, { items: rows.map(normalizeCommentRow) });
  }
  if (!id) return json(res, 400, { error: 'id is required' });
  if (req.method === 'PATCH') {
    const rows = await supabaseRequest(`deal_comments?id=eq.${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ body: value(req.body?.body || '', 500) }),
    });
    return json(res, 200, { item: normalizeCommentRow(rows?.[0]) });
  }
  if (req.method === 'DELETE') {
    await supabaseRequest(`deal_comments?id=eq.${encodeURIComponent(id)}`, { method: 'DELETE', headers: { Prefer: 'return=minimal' } });
    return json(res, 200, { ok: true });
  }
  res.setHeader('Allow', 'GET, PATCH, DELETE');
  return json(res, 405, { error: 'Method not allowed' });
}

async function handleReports(req, res, url) {
  const id = value(req.body?.id || url.searchParams.get('id') || '', 120);
  if (req.method === 'GET') {
    const rows = await safeRows('admin_reports?order=created_at.desc&limit=300', []);
    return json(res, 200, { items: rows.map(normalizeReport) });
  }
  if (req.method === 'POST') {
    const now = new Date().toISOString();
    const payload = {
      target_type: value(req.body?.targetType || 'deal', 40),
      target_id: value(req.body?.targetId || '', 240),
      reason: value(req.body?.reason || '', 200),
      memo: value(req.body?.memo || '', 2000),
      reporter: value(req.body?.reporter || 'admin', 120),
      status: value(req.body?.status || 'pending', 40),
      created_at: now,
      updated_at: now,
    };
    const rows = await supabaseRequest('admin_reports', { method: 'POST', body: JSON.stringify([payload]) });
    return json(res, 201, { item: normalizeReport(rows?.[0] || payload) });
  }
  if (!id) return json(res, 400, { error: 'id is required' });
  if (req.method === 'PATCH') {
    const payload = {
      status: value(req.body?.status || 'pending', 40),
      memo: value(req.body?.memo || '', 2000),
      updated_at: new Date().toISOString(),
    };
    const rows = await supabaseRequest(`admin_reports?id=eq.${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    return json(res, 200, { item: normalizeReport(rows?.[0]) });
  }
  if (req.method === 'DELETE') {
    await supabaseRequest(`admin_reports?id=eq.${encodeURIComponent(id)}`, { method: 'DELETE', headers: { Prefer: 'return=minimal' } });
    return json(res, 200, { ok: true });
  }
  res.setHeader('Allow', 'GET, POST, PATCH, DELETE');
  return json(res, 405, { error: 'Method not allowed' });
}

async function handleNotices(req, res, url) {
  const id = value(req.body?.id || url.searchParams.get('id') || '', 120);
  if (req.method === 'GET') {
    const rows = await safeRows('admin_notices?order=created_at.desc&limit=200', []);
    return json(res, 200, { items: rows.map(normalizeNotice) });
  }
  if (req.method === 'POST') {
    const now = new Date().toISOString();
    const payload = {
      title: value(req.body?.title || '', 160),
      body: value(req.body?.body || '', 5000),
      pinned: bool(req.body?.pinned),
      published: req.body?.published !== false,
      starts_at: value(req.body?.startsAt || '', 40) || null,
      ends_at: value(req.body?.endsAt || '', 40) || null,
      created_at: now,
      updated_at: now,
    };
    if (!payload.title) return json(res, 400, { error: 'title is required' });
    const rows = await supabaseRequest('admin_notices', { method: 'POST', body: JSON.stringify([payload]) });
    return json(res, 201, { item: normalizeNotice(rows?.[0] || payload) });
  }
  if (!id) return json(res, 400, { error: 'id is required' });
  if (req.method === 'PATCH') {
    const payload = {
      title: value(req.body?.title || '', 160),
      body: value(req.body?.body || '', 5000),
      pinned: bool(req.body?.pinned),
      published: req.body?.published !== false,
      starts_at: value(req.body?.startsAt || '', 40) || null,
      ends_at: value(req.body?.endsAt || '', 40) || null,
      updated_at: new Date().toISOString(),
    };
    const rows = await supabaseRequest(`admin_notices?id=eq.${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    return json(res, 200, { item: normalizeNotice(rows?.[0]) });
  }
  if (req.method === 'DELETE') {
    await supabaseRequest(`admin_notices?id=eq.${encodeURIComponent(id)}`, { method: 'DELETE', headers: { Prefer: 'return=minimal' } });
    return json(res, 200, { ok: true });
  }
  res.setHeader('Allow', 'GET, POST, PATCH, DELETE');
  return json(res, 405, { error: 'Method not allowed' });
}

async function handleBoard(req, res, url) {
  const id = value(req.body?.id || url.searchParams.get('id') || '', 120);
  if (req.method === 'GET') {
    const rows = await safeRows('board_posts?deleted_at=is.null&order=created_at.desc&limit=200', []);
    return json(res, 200, { items: rows.map(normalizeBoardRow) });
  }
  if (!id) return json(res, 400, { error: 'id is required' });
  const boardId = parseBoardId(id);
  if (req.method === 'PATCH') {
    const payload = { ...mapBoardPayload(req.body || {}), updated_at: new Date().toISOString() };
    const rows = await supabaseRequest(`board_posts?id=eq.${encodeURIComponent(boardId)}&deleted_at=is.null`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    return json(res, 200, { item: normalizeBoardRow(rows?.[0]) });
  }
  if (req.method === 'DELETE') {
    await supabaseRequest(`board_posts?id=eq.${encodeURIComponent(boardId)}&deleted_at=is.null`, {
      method: 'PATCH',
      body: JSON.stringify({ deleted_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    });
    return json(res, 200, { ok: true });
  }
  res.setHeader('Allow', 'GET, PATCH, DELETE');
  return json(res, 405, { error: 'Method not allowed' });
}

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
  const url = new URL(req.url, 'http://localhost');
  const resource = url.searchParams.get('resource') || req.query?.resource || 'status';

  try {
    if (resource === 'status' && req.method === 'GET') {
      return json(res, 200, { configured: isConfigured(), admin: getAdmin(req) });
    }

    if (resource === 'login' && req.method === 'POST') {
      if (!isConfigured()) return json(res, 503, { error: 'admin is not configured', setupRequired: true });
      const password = String(req.body?.password || '');
      if (!process.env.ADMIN_PASSWORD || password !== process.env.ADMIN_PASSWORD) {
        return json(res, 401, { error: 'invalid admin password' });
      }
      const admin = { role: 'admin', email: 'password-admin', name: '관리자', provider: 'password' };
      setCookie(req, res, ADMIN_COOKIE, createSession(admin), 60 * 60 * 12);
      return json(res, 200, { admin });
    }

    if (resource === 'logout' && req.method === 'POST') {
      clearCookie(req, res, ADMIN_COOKIE);
      return json(res, 200, { ok: true });
    }

    const admin = requireAdmin(req, res);
    if (!admin) return;

    if (resource === 'dashboard') return handleDashboard(req, res);
    if (resource === 'deals') return handleDeals(req, res, url);
    if (resource === 'users') return handleUsers(req, res, url);
    if (resource === 'comments') return handleComments(req, res, url);
    if (resource === 'reports') return handleReports(req, res, url);
    if (resource === 'notices') return handleNotices(req, res, url);
    if (resource === 'board') return handleBoard(req, res, url);

    return json(res, 404, { error: 'unknown admin resource' });
  } catch (error) {
    return json(res, 500, { error: error.message || 'admin server error' });
  }
};
