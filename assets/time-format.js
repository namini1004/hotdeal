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

  function dayDiffFromLocalMidnight(now, then){
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const targetDay = new Date(then.getFullYear(), then.getMonth(), then.getDate());
    return Math.max(0, Math.floor((today.getTime() - targetDay.getTime()) / 86400000));
  }

  function toRelativeKorean(value, options){
    const ms = parseMs(value);
    if(!ms) return options?.fallback || '';

    const now = options?.now ? new Date(options.now) : new Date();
    const then = new Date(ms);
    const diffMin = Math.max(0, Math.floor((now.getTime() - ms) / 60000));

    if(diffMin < 5) return '방금 전';
    if(diffMin < 60) return `${diffMin}분전`;

    const diffDay = dayDiffFromLocalMidnight(now, then);
    if(diffDay === 1) return '어제';
    if(diffDay === 2) return '그저께';
    if(diffDay > 2) return `${diffDay}일전`;

    const diffHour = Math.floor(diffMin / 60);
    if(diffHour < 24) return `${diffHour}시간전`;

    return options?.fallback || absoluteKorean(value);
  }

  global.TimeFormat = {
    parseMs,
    absoluteKorean,
    toRelativeKorean,
  };
})(window);
