(function(global){
  function parseMs(value){
    if(!value) return 0;
    const ms = Date.parse(String(value));
    return Number.isFinite(ms) ? ms : 0;
  }

  function absoluteKorean(value){
    const ms = parseMs(value);
    if(!ms) return '';
    return new Date(ms).toLocaleString('ko-KR', {
      month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit'
    });
  }

  function toRelativeKorean(value, options){
    const ms = parseMs(value);
    if(!ms) return options?.fallback || '';
    const nowMs = Date.now();
    const diffMin = Math.max(0, Math.floor((nowMs - ms) / 60000));
    if(diffMin < 60) return `${Math.max(1, diffMin)}분 전`;
    const diffHour = Math.floor(diffMin / 60);
    if(diffHour >= 1) return `${diffHour}시간 전`;
    return options?.fallback || absoluteKorean(value);
  }

  global.TimeFormat = {
    parseMs,
    absoluteKorean,
    toRelativeKorean,
  };
})(window);
