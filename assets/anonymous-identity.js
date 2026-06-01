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
    return `${ADJECTIVES[h % ADJECTIVES.length]} ${NOUNS[Math.floor(h / 7) % NOUNS.length]}${String(h).slice(-2)}`;
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

  function getUser(){
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
    const user = getUser();
    try{ localStorage.setItem(USER_CACHE_KEY, JSON.stringify(user)); }catch(_){ }
    return user;
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
        headers.set('X-Gaji-Nickname', getNickname());
        nextInit.headers = headers;
        nextInit.body = decorateBody(nextInit.body);
      }
      return nativeFetch(input, nextInit);
    };
  }

  window.GajiIdentity = {
    getDeviceId,
    getNickname,
    setNickname(nickname){
      const clean = String(nickname || '').trim().replace(/\s+/g, ' ').slice(0, 24);
      if(clean) localStorage.setItem(NICK_KEY, clean);
      return cacheUser();
    },
    getUser: cacheUser,
  };

  cacheUser();
})();
