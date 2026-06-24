(function(global){
  function parseMs(value){
    if(value === undefined || value === null || value === '') return 0;
    const raw = String(value).trim();
    if(!raw) return 0;

    const relative = raw.match(/^(\d+)\s*(분|시간|일)\s*전$/);
    if(relative){
      const amount = Number(relative[1]);
      const unit = relative[2];
      if(Number.isFinite(amount)){
        const unitMs = unit === '분' ? 60000 : unit === '시간' ? 3600000 : 86400000;
        return Date.now() - amount * unitMs;
      }
    }
    if(/^방금\s*전?$/.test(raw)) return Date.now();
    if(raw === '어제') return Date.now() - 86400000;
    if(raw === '그저께') return Date.now() - 172800000;

    const dateOnly = raw.match(/^(\d{4})[-./](\d{1,2})[-./](\d{1,2})\.?$/);
    if(dateOnly){
      const local = new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
      return Number.isFinite(local.getTime()) ? local.getTime() : 0;
    }

    const monthDay = raw.match(/^(\d{1,2})[-./](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?$/);
    if(monthDay){
      const now = new Date();
      const year = now.getFullYear();
      const month = Number(monthDay[1]) - 1;
      const day = Number(monthDay[2]);
      const hour = Number(monthDay[3] || 0);
      const minute = Number(monthDay[4] || 0);
      const local = new Date(year, month, day, hour, minute);
      return Number.isFinite(local.getTime()) ? local.getTime() : 0;
    }

    const normalized = raw
      .replace(/^(\d{4})\.(\d{1,2})\.(\d{1,2})\.?(?:\s+(\d{1,2}):(\d{2}))?$/, (_, y, m, d, h = '00', min = '00') => `${y}-${m}-${d} ${h}:${min}`)
      .replace(/^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?$/, (_, y, m, d, h, min, sec = '00') => `${y}-${m}-${d}T${h}:${min}:${sec}`);
    const ms = Date.parse(normalized);
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

    const now = options?.now ? new Date(options.now) : new Date();
    const diffMin = Math.max(0, Math.floor((now.getTime() - ms) / 60000));

    if(diffMin < 1) return '방금 전';
    if(diffMin < 60) return `${diffMin}분 전`;

    const diffHour = Math.floor(diffMin / 60);
    if(diffHour < 24) return `${diffHour}시간 전`;

    return `${Math.floor(diffHour / 24)}일 전`;
  }

  global.TimeFormat = {
    parseMs,
    absoluteKorean,
    toRelativeKorean,
  };
})(window);
