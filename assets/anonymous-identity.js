(function(){
  const DEVICE_KEY = 'gaji_device_id_v1';
  const NICK_KEY = 'gaji_guest_nickname_v1';
  const USER_CACHE_KEY = 'gaji_auth_user_cache_v1';
  const DEVICE_COOKIE = 'gaji_device_id';
  const ADJECTIVES = [
    '알뜰한','야무진','빠른','느긋한','상냥한','반짝이는','차분한','든든한','포근한','신나는','싱싱한','용감한','꼼꼼한','재빠른','귀여운','활기찬','조용한','멋진','똑똑한','따뜻한','시원한','향긋한','즐거운','유쾌한','부지런한','당찬','섬세한','빛나는','푸근한','산뜻한','달콤한','고요한','기발한','믿음직한','새침한','명랑한','정겨운','여유로운','예리한','반가운','환한','튼튼한','근사한','재치있는','소중한','깔끔한','선명한','싱그러운','포근포근한','소박한','담백한','귀중한','깜찍한','느낌있는','다정한','맑은','든든든한','멋스러운','민첩한','부드러운','사려깊은','선한','성실한','순한','쾌활한','튼실한','특별한','편안한','활발한','희망찬','날렵한','노련한','단단한','당돌한','따사로운','말랑한','바른','뽀송한','상큼한','센스있는','신중한','씩씩한','아늑한','열정적인','영리한','온화한','우아한','유연한','은은한','재미난','정직한','지혜로운','초롱한','친근한','튼튼씩씩한','평온한','화사한','활력있는','훈훈한','흥겨운','반짝반짝한'
  ];
  const NOUNS = [
    '가지','딜러','장바구니','별빛','구름','파도','보라','알림이','탐험가','수집가','감자','고구마','당근','토마토','브로콜리','오이','호박','완두콩','양파','마늘','버섯','옥수수','피망','상추','새싹','나뭇잎','꽃잎','햇살','달빛','별똥별','무지개','바람','산책가','여행자','발견자','구매요정','가격요정','쿠폰요정','배송요정','할인왕','검색왕','리뷰어','체커','감별사','온도계','메모장','책갈피','보물상자','지갑','동전','영수증','바구니','보따리','창고','서랍','램프','나침반','지도','망원경','돋보기','시계','종소리','메신저','비둘기','고래','돌고래','펭귄','수달','고양이','강아지','토끼','햄스터','다람쥐','여우','판다','코알라','사슴','올빼미','참새','제비','나비','꿀벌','잠자리','무당벌레','문어','거북이','해파리','조개','진주','자갈','모래','소나무','대나무','민들레','라벤더','로즈마리','바질','민트','커피콩','머그컵','노트','연필'
  ];

  function randomId(){
    if(window.crypto?.randomUUID) return window.crypto.randomUUID().replace(/-/g, '');
    return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 14)}`;
  }

  function hash(text){
    let n = 0;
    for(let i = 0; i < text.length; i += 1) n = ((n << 5) - n + text.charCodeAt(i)) | 0;
    return Math.abs(n);
  }

  function readCookie(name){
    const key = `${name}=`;
    return String(document.cookie || '').split(';').map(v => v.trim()).find(v => v.startsWith(key))?.slice(key.length) || '';
  }

  function getDeviceId(){
    let id = localStorage.getItem(DEVICE_KEY);
    if(!id){
      const cookieId = readCookie(DEVICE_COOKIE);
      if(cookieId){
        try{ id = decodeURIComponent(cookieId); }catch(_){ id = cookieId; }
      }else{
        id = randomId();
      }
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

  function nicknameInitials(nickname = getNickname()){
    const name = String(nickname || '가지').trim().replace(/\s+/g, ' ');
    if(!name) return '가';
    const parts = name.split(' ').filter(Boolean);
    const first = parts[0]?.charAt(0) || '';
    const second = parts[1]?.charAt(0) || parts[0]?.charAt(1) || '';
    return (first + second).replace(/[&<>"']/g, '') || '가';
  }

  function avatarUrl(nickname = getNickname()){
    const name = String(nickname || '가지').trim() || '가지';
    const h = hash(name);
    const palettes = [
      ['#4c1d95','#7c3aed'],
      ['#312e81','#6366f1'],
      ['#164e63','#0891b2'],
      ['#14532d','#16a34a'],
      ['#7c2d12','#ea580c'],
      ['#831843','#db2777'],
      ['#111827','#6d28d9'],
      ['#1f2937','#0f766e']
    ];
    const [bg] = palettes[h % palettes.length];
    const initial = nicknameInitials(name);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96"><rect width="96" height="96" rx="48" fill="${bg}"/><text x="48" y="48" text-anchor="middle" dominant-baseline="central" font-family="Arial, sans-serif" font-size="34" font-weight="900" fill="#fff">${initial}</text></svg>`;
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
    if(cached && cached.anonymous === false) return cached;
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
    getInitials: nicknameInitials,
    generateNickname,
    regenerateNickname,
    getAvatarUrl: avatarUrl,
    setNickname,
    getUser: cacheUser,
  };

  cacheUser();
})();
