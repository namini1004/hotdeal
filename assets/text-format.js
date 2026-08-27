(function(){
  var RICH_TEXT_PREFIX = '<!--gaji-rich-v1-->';
  var SAFE_RICH_TAGS = {
    p: true, div: true, br: true, hr: true,
    strong: true, em: true, span: true, a: true,
    h1: true, h2: true, h3: true,
    ul: true, ol: true, li: true, blockquote: true,
    table: true, thead: true, tbody: true, tr: true, th: true, td: true
  };
  var SAFE_RICH_CLASSES = {
    'gaji-align-center': true,
    'gaji-align-right': true,
    'gaji-align-justify': true,
    'gaji-text-xl': true,
    'gaji-text-lg': true,
    'gaji-text-sm': true,
    'gaji-font-bold': true,
    'gaji-underline': true,
    'gaji-quote': true,
    'gaji-rich-table': true
  };

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

  function richTextFallback(source){
    var text = String(source || '')
      .replace(/<br\s*\/?\s*>/gi, '\n')
      .replace(/<\/(?:p|div|h[1-3]|li|blockquote|tr)>/gi, '\n')
      .replace(/<[^>]*>/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    if(!text) return '';
    return '<div class="gaji-rich"><p>' + linkifyText(text).replace(/\n/g, '<br>') + '</p></div>';
  }

  function sanitizeRichHtml(source){
    if(typeof DOMParser === 'undefined') return richTextFallback(source);

    var doc = new DOMParser().parseFromString(String(source || ''), 'text/html');

    function sanitizeNode(node){
      if(node.nodeType === 3) return escapeHtml(node.nodeValue || '');
      if(node.nodeType !== 1) return '';

      var tag = String(node.tagName || '').toLowerCase();
      if(['script', 'style', 'noscript', 'iframe', 'object', 'svg', 'canvas', 'img'].indexOf(tag) >= 0){
        return '';
      }

      var children = Array.from(node.childNodes || []).map(sanitizeNode).join('');
      if(!SAFE_RICH_TAGS[tag]) return children;
      if(tag === 'br' || tag === 'hr') return '<' + tag + '>';

      var classes = String(node.getAttribute('class') || '')
        .split(/\s+/)
        .filter(function(name){ return SAFE_RICH_CLASSES[name]; });
      var attrs = classes.length ? ' class="' + escapeAttr(classes.join(' ')) + '"' : '';

      if(tag === 'a'){
        var href = toSafeUrl(node.getAttribute('href') || '');
        if(!href || !children.trim()) return children;
        attrs += ' href="' + escapeAttr(href) + '" target="_blank" rel="noopener noreferrer nofollow"';
      }
      return '<' + tag + attrs + '>' + children + '</' + tag + '>';
    }

    var rendered = Array.from(doc.body.childNodes || []).map(sanitizeNode).join('');
    return rendered ? '<div class="gaji-rich">' + rendered + '</div>' : '';
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

  function isTableSeparator(line){
    var s = String(line || '').trim();
    if(!s) return false;
    var cols = s.replace(/^\||\|$/g, '').split('|').map(function(v){ return v.trim(); });
    if(!cols.length) return false;
    return cols.every(function(c){ return /^:?-{3,}:?$/.test(c); });
  }

  function splitTableCols(line){
    return String(line || '').trim().replace(/^\||\|$/g, '').split('|').map(function(v){ return v.trim(); });
  }

  function isTableLike(line){
    var s = String(line || '').trim();
    return s.indexOf('|') >= 0 && /^\|?.+\|.+\|?$/.test(s);
  }

  function markdownToHtml(markdown){
    var rawInput = String(markdown || '');
    var richInput = rawInput.replace(/^\s+/, '');
    if(richInput.indexOf(RICH_TEXT_PREFIX) === 0){
      return sanitizeRichHtml(richInput.slice(RICH_TEXT_PREFIX.length));
    }

    var input = rawInput
      .replace(/\r\n?/g, '\n')
      .replace(/\\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n');

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

    for(var i = 0; i < lines.length; i += 1){
      var line = lines[i];

      if(isTableLike(line) && i + 1 < lines.length && isTableSeparator(lines[i + 1])){
        closeUl();
        var headCols = splitTableCols(line);
        html.push('<div class="md-table-wrap"><table class="md-table"><thead><tr>' + headCols.map(function(col){ return '<th>' + parseInline(col) + '</th>'; }).join('') + '</tr></thead><tbody>');
        i += 2;
        while(i < lines.length && isTableLike(lines[i]) && !isTableSeparator(lines[i])){
          var rowCols = splitTableCols(lines[i]);
          html.push('<tr>' + rowCols.map(function(col){ return '<td>' + parseInline(col) + '</td>'; }).join('') + '</tr>');
          i += 1;
        }
        html.push('</tbody></table></div>');
        i -= 1;
        continue;
      }

      var ulMatch = line.match(/^\s*[-*]\s+(.+)$/);
      if(ulMatch){
        if(!inUl){
          html.push('<ul>');
          inUl = true;
        }
        html.push('<li>' + parseInline(ulMatch[1]) + '</li>');
        continue;
      }

      var hMatch = line.match(/^\s*(#{1,3})\s+(.+)$/);
      if(hMatch){
        closeUl();
        var level = Math.max(1, Math.min(3, hMatch[1].length));
        html.push('<h' + level + '>' + parseInline(hMatch[2]) + '</h' + level + '>');
        continue;
      }

      closeUl();

      if(!line.trim()){
        html.push('');
        continue;
      }

      html.push('<p>' + parseInline(line) + '</p>');
    }

    closeUl();

    return html.join('\n');
  }

  window.TextFormat = {
    escapeHtml: escapeHtml,
    linkifyText: linkifyText,
    markdownToHtml: markdownToHtml,
    sanitizeRichHtml: sanitizeRichHtml
  };
})();
