(function(){
  const DEVICE_KEY = 'gaji_device_id_v1';
  const NICK_KEY = 'gaji_guest_nickname_v1';
  const USER_CACHE_KEY = 'gaji_auth_user_cache_v1';
  const DEVICE_COOKIE = 'gaji_device_id';
  const ADJECTIVES = ['빠른','상냥한','반짝이는','차분한','야무진','든든한','포근한','신나는','싱싱한','알뜰한'];
  const NOUNS = ['가지','딜러','장바구니','별빛','구름','파도','보라','알림이','탐험가','수집가'];

  function randomId(){
    if(window.crypto?.randomUUID) return window.crypto.randomUUID().replace(/-/g, '');
    return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 14)}`;
  }

  function hash(text){
    let n = 0;
    for(let i = 0; i < text.length; i += 1) n = ((n << 5) - n + text.charCodeAt(i)) | 0;
    return Math.abs(n);
  }

  function getDeviceId(){
    let id = localStorage.getItem(DEVICE_KEY);
    if(!id){
      id = randomId();
      localStorage.setItem(DEVICE_KEY, id);
    }
    document.cookie = `${DEVICE_COOKIE}=${encodeURIComponent(id)}; Max-Age=31536000; Path=/; SameSite=Lax`;
    return id;
  }

  function makeNickname(id){
    const h = hash(id);
    return `${ADJECTIVES[h % ADJECTIVES.length]} ${NOUNS[Math.floor(h / 7) % NOUNS.length]}${String(h % 100).padStart(2, '0')}`;
  }

  function normalizeNickname(nickname){
    return String(nickname || '').trim().replace(/\s+/g, ' ').slice(0, 24);
  }

  function getNickname(){
    const id = getDeviceId();
    let nickname = localStorage.getItem(NICK_KEY);
    if(!nickname){
      nickname = makeNickname(id);
      localStorage.setItem(NICK_KEY, nickname);
    }
    return nickname;
  }

  function headerSafe(value){
    return encodeURIComponent(String(value || ''));
  }

  function avatarUrl(nickname = getNickname()){
    const name = String(nickname || '가지').trim() || '가지';
    const h = hash(name);
    const palettes = [
      ['#f3edff','#7c3aed','#4c1d95'],
      ['#eef2ff','#6366f1','#312e81'],
      ['#ecfeff','#0891b2','#164e63'],
      ['#f0fdf4','#16a34a','#14532d'],
      ['#fff7ed','#ea580c','#7c2d12'],
      ['#fdf2f8','#db2777','#831843']
    ];
    const [bg, mid, ink] = palettes[h % palettes.length];
    const initial = name.charAt(0).replace(/[&<>"']/g, '');
    const tilt = (h % 17) - 8;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96"><rect width="96" height="96" rx="48" fill="${bg}"/><circle cx="66" cy="28" r="18" fill="${mid}" opacity=".18"/><circle cx="29" cy="72" r="24" fill="${mid}" opacity=".12"/><g transform="translate(48 49) rotate(${tilt})"><ellipse cx="0" cy="6" rx="16" ry="22" fill="${mid}"/><path d="M6-16c8-6 16-6 22-1-7 1-14 5-18 12" fill="${ink}"/></g><text x="48" y="60" text-anchor="middle" font-family="Arial, sans-serif" font-size="30" font-weight="800" fill="#fff">${initial}</text></svg>`;
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  }

  function readCachedUser(){
    try{
      const parsed = JSON.parse(localStorage.getItem(USER_CACHE_KEY) || 'null');
      return parsed && typeof parsed === 'object' ? parsed : null;
    }catch(_){ return null; }
  }

  function writeCachedUser(user){
    try{ localStorage.setItem(USER_CACHE_KEY, JSON.stringify(user)); }catch(_){ }
    return user;
  }

  function getAnonymousUser(){
    const deviceId = getDeviceId();
    const nickname = getNickname();
    return {
      id: `anon:${deviceId}`,
      provider: 'anonymous',
      providerId: deviceId,
      name: nickname,
      nickname,
      email: '',
      anonymous: true
    };
  }

  function cacheUser(){
    const cached = readCachedUser();
    if(cached && cached.anonymous === false) return cached;
    return writeCachedUser(getAnonymousUser());
  }

  function setNickname(nickname){
    const clean = normalizeNickname(nickname);
    if(!clean) return cacheUser();
    localStorage.setItem(NICK_KEY, clean);
    const cached = readCachedUser();
    if(cached && cached.anonymous === false){
      return writeCachedUser({ ...cached, name: clean, nickname: clean });
    }
    return writeCachedUser(getAnonymousUser());
  }

  function generateNickname(seed = randomId()){
    return makeNickname(seed);
  }

  function regenerateNickname(){
    const seed = `${getDeviceId()}:${Date.now()}:${Math.random()}`;
    return setNickname(generateNickname(seed));
  }

  function decorateBody(body){
    if(!body || typeof body !== 'string') return body;
    try{
      const parsed = JSON.parse(body);
      if(parsed && typeof parsed === 'object' && !Array.isArray(parsed)){
        parsed.deviceId = parsed.deviceId || getDeviceId();
        parsed.nickname = parsed.nickname || getNickname();
        parsed.author = parsed.author || getNickname();
        return JSON.stringify(parsed);
      }
    }catch(_){ }
    return body;
  }

  const nativeFetch = window.fetch?.bind(window);
  if(nativeFetch && !window.__gajiAnonymousFetchPatched){
    window.__gajiAnonymousFetchPatched = true;
    window.fetch = function(input, init){
      const nextInit = { ...(init || {}) };
      const url = typeof input === 'string' ? input : input?.url || '';
      const isApi = /^\/api\//.test(url) || String(url).startsWith(`${location.origin}/api/`);
      if(isApi){
        const headers = new Headers(nextInit.headers || (typeof input !== 'string' ? input.headers : undefined) || {});
        headers.set('X-Gaji-Device-Id', getDeviceId());
        headers.set('X-Gaji-Nickname', headerSafe(getNickname()));
        nextInit.headers = headers;
        nextInit.body = decorateBody(nextInit.body);
      }
      return nativeFetch(input, nextInit);
    };
  }

  window.GajiIdentity = {
    getDeviceId,
    getNickname,
    generateNickname,
    regenerateNickname,
    getAvatarUrl: avatarUrl,
    setNickname,
    getUser: cacheUser,
  };

  cacheUser();
})();
