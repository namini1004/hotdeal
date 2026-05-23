(function(){
  function escapeHtml(text){
    return String(text || '').replace(/[&<>"']/g, function(ch){
      return ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[ch];
    });
  }

  function escapeAttr(text){
    return String(text || '').replace(/"/g, '&quot;');
  }

  function toSafeUrl(raw){
    try{
      var url = new URL(String(raw || ''), location.origin);
      var protocol = (url.protocol || '').toLowerCase();
      if(protocol === 'http:' || protocol === 'https:') return url.href;
      return '';
    }catch(_){
      return '';
    }
  }

  function linkifyText(text){
    var escaped = escapeHtml(text || '');
    return escaped.replace(/(https?:\/\/[^\s<]+)/g, function(url){
      var safe = toSafeUrl(url);
      if(!safe) return escapeHtml(url);
      var label = escapeHtml(url);
      return '<a href="' + escapeAttr(safe) + '" target="_blank" rel="noopener noreferrer nofollow">' + label + '</a>';
    });
  }

  function parseInline(md){
    var text = String(md || '');
    var placeholders = [];

    text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, function(_, label, url){
      var safe = toSafeUrl(url);
      if(!safe) return escapeHtml(label) + ' (' + escapeHtml(url) + ')';
      var token = '%%LINK_' + placeholders.length + '%%';
      placeholders.push('<a href="' + escapeAttr(safe) + '" target="_blank" rel="noopener noreferrer nofollow">' + escapeHtml(label) + '</a>');
      return token;
    });

    text = escapeHtml(text);
    text = text
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');

    text = text.replace(/(https?:\/\/[^\s<]+)/g, function(url){
      var safe = toSafeUrl(url);
      if(!safe) return url;
      return '<a href="' + escapeAttr(safe) + '" target="_blank" rel="noopener noreferrer nofollow">' + url + '</a>';
    });

    placeholders.forEach(function(html, idx){
      text = text.replace('%%LINK_' + idx + '%%', html);
    });

    return text;
  }

  function markdownToHtml(markdown){
    var input = String(markdown || '').replace(/\r\n?/g, '\n');
    if(!input.trim()) return '';

    var lines = input.split('\n');
    var html = [];
    var inUl = false;

    function closeUl(){
      if(inUl){
        html.push('</ul>');
        inUl = false;
      }
    }

    lines.forEach(function(line){
      var ulMatch = line.match(/^\s*[-*]\s+(.+)$/);
      if(ulMatch){
        if(!inUl){
          html.push('<ul>');
          inUl = true;
        }
        html.push('<li>' + parseInline(ulMatch[1]) + '</li>');
        return;
      }

      closeUl();

      if(!line.trim()){
        html.push('');
        return;
      }

      html.push('<p>' + parseInline(line) + '</p>');
    });

    closeUl();

    return html.join('\n');
  }

  window.TextFormat = {
    escapeHtml: escapeHtml,
    linkifyText: linkifyText,
    markdownToHtml: markdownToHtml
  };
})();
