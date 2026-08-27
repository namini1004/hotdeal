#!/usr/bin/env python3
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests
try:
    from hotdeal_quality_signals import (
        QUALITY_SIGNAL_PARSER_VERSION,
        analyze_comment_quality,
        extract_comment_signal_text,
    )
except ModuleNotFoundError:
    from scripts.hotdeal_quality_signals import (
        QUALITY_SIGNAL_PARSER_VERSION,
        analyze_comment_quality,
        extract_comment_signal_text,
    )

LIST_URL = "https://m.ruliweb.com/market/board/1020"
BASE = "https://bbs.ruliweb.com"
MAX_PAGES = 12
INCREMENTAL_TAIL_SAMPLE_SIZE = int(os.environ.get("HOTDEAL_RULIWEB_INCREMENTAL_TAIL_SAMPLE_SIZE", "3"))
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "ruliweb_hotdeals_1day.json"
KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0"}
RICH_TEXT_PREFIX = "<!--gaji-rich-v1-->"


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def load_previous_items():
    if not JSON_PATH.exists():
        return []
    try:
        data = json.loads(JSON_PATH.read_text(encoding='utf-8'))
        return list(data.get('items') or [])
    except Exception:
        return []


def build_previous_link_keys(items):
    return {
        str(item.get('sourceLink') or '').strip()
        for item in items or []
        if str(item.get('sourceLink') or '').strip()
    }


def row_exists_in_previous(row, previous_keys) -> bool:
    source_link = str(row.get('sourceLink') or '').strip()
    return bool(source_link and source_link in previous_keys)


def page_tail_seen_in_previous(rows, previous_keys) -> bool:
    if not rows or not previous_keys:
        return False
    sample_size = max(1, INCREMENTAL_TAIL_SAMPLE_SIZE)
    return any(row_exists_in_previous(row, previous_keys) for row in rows[-sample_size:])


def to_mobile_read_url(source_link: str, post_id: str) -> str:
    if post_id and str(post_id).isdigit():
        return f"https://m.ruliweb.com/market/board/1020/read/{post_id}"
    return source_link


def to_proxy_image_url(src: str) -> str:
    raw = clean(src)
    if not raw:
        return ''
    if raw.startswith('//'):
        raw = f'https:{raw}'
    if 'ruliweb.com' in raw:
        return f"/api/image-proxy?url={quote(raw, safe='')}"
    return raw


def parse_time_to_datetime(text: str, now: datetime) -> datetime:
    t = (text or "").strip()
    # HH:MM => 오늘
    hm = re.match(r"^(\d{2}):(\d{2})$", t)
    if hm:
        return now.replace(hour=int(hm.group(1)), minute=int(hm.group(2)), second=0, microsecond=0)
    # YYYY.MM.DD
    d = re.match(r"^(\d{4})\.(\d{2})\.(\d{2})$", t)
    if d:
        return datetime(int(d.group(1)), int(d.group(2)), int(d.group(3)), 0, 0, tzinfo=KST)
    return now


def parse_numeric_price_value(price_text: str) -> int:
    s = (price_text or '').replace(' ', '')
    m = re.search(r'[0-9][0-9,]*', s)
    if not m:
        return 0
    n = int(m.group(0).replace(',', ''))
    if '만원' in s:
        return n * 10000
    if '천원' in s:
        return n * 1000
    return n


def extract_best_price(text: str) -> str:
    t = text or ''
    # '52 560원'처럼 콤마가 빠진 표기를 우선 보정
    t = re.sub(r'(?<!\d)(\d{1,3})\s{1,2}(\d{3})(\s*원)', r'\1,\2\3', t)

    candidates = []

    def push(raw: str):
        normalized = (raw or '').replace(' ', '')
        normalized = re.sub(r'[\.,;:!?]+$', '', normalized)
        if not normalized:
            return
        candidates.append((normalized, parse_numeric_price_value(normalized), (',' in normalized)))

    # 1) 원/천원/만원 계열
    for m in re.finditer(r'([0-9][0-9,]*\s*(?:만원대|천원대|원대|만원|천원|원))(?![가-힣A-Za-z])', t):
        push(m.group(1))

    # 2) 통화기호(₩/￦) + 숫자
    for m in re.finditer(r'([₩￦]\s*[0-9][0-9,]{2,})(?![0-9])', t):
        s = re.sub(r'[₩￦\s]+', '', m.group(1))
        s = re.sub(r'[\.,;:!?]+$', '', s)
        push(f'{s}원')

    # 3) 통화기호/원 없이 천단위 콤마 숫자
    for m in re.finditer(r'(^|[^0-9])([0-9]{1,3}(?:,[0-9]{3})+)(?![0-9])', t):
        push(f'{m.group(2)}원')

    if not candidates:
        return ''

    over_1k = [c for c in candidates if c[1] >= 1000]
    pool = over_1k if over_1k else candidates
    pool.sort(key=lambda x: (x[2], x[1], len(x[0])), reverse=True)
    return pool[0][0]


def parse_rows(page_html: str, seen: set):
    rows = re.findall(r'<tr class="table_body[^\"]*">[\s\S]*?</tr>', page_html)
    items = []

    for row in rows:
        if '>공지<' in row:
            continue

        title_m = re.search(r'subject_link[^\"]*"\s+href="([^"]+)"[^>]*>([\s\S]*?)</a>', row, re.S)
        if not title_m:
            continue
        source_link = clean(title_m.group(1))
        post_id_m = re.search(r'/read/(\d+)', source_link)
        post_id = post_id_m.group(1) if post_id_m else source_link
        source_link = to_mobile_read_url(source_link, post_id)
        if post_id in seen:
            continue
        seen.add(post_id)

        title = clean(re.sub(r'<[^>]+>', '', title_m.group(2)))
        category_m = re.search(r'<td class="divsn">[\s\S]*?<strong>(.*?)</strong>', row, re.S)
        category = clean(category_m.group(1)) if category_m else '기타'

        comments_m = re.search(r'class="num_reply"[^>]*>\s*\(([0-9,]+)\)', row)
        comments = int((comments_m.group(1).replace(',', '') if comments_m else '0') or '0')

        likes_m = re.search(r'<td class="recom">\s*([0-9,]+)\s*</td>', row, re.S)
        likes = int((likes_m.group(1).replace(',', '') if likes_m else '0') or '0')

        views_m = re.search(r'<td class="hit">\s*([0-9,]+)\s*</td>', row, re.S)
        views = int((views_m.group(1).replace(',', '') if views_m else '0') or '0')

        time_m = re.search(r'<td class="time">\s*([^<]+)\s*</td>', row, re.S)
        time_text = clean(time_m.group(1)) if time_m else ''

        price = extract_best_price(title) or '가격 정보 확인'
        if price == '가격 정보 확인' and '무료' in title:
            price = '무료'
        elif price == '가격 정보 확인' and '다양' in title:
            price = '다양'

        items.append(
            {
                "id": post_id,
                "title": title or "제목 없음",
                "area": "루딜",
                "dist": category,
                "time": time_text,
                "price": price,
                "likes": likes,
                "views": views,
                "comments": comments,
                "category": category,
                "desc": "",
                "img": "",
                "buyLink": "",
                "sourceLink": source_link,
                "source": "ruliweb",
            }
        )

    return items


def parse_detail_like_count(detail_html: str) -> int:
    like_m = re.search(r'class=["\'][^"\']*like-value[^"\']*["\'][^>]*>\s*([0-9,]+)\s*<', detail_html, re.I)
    return int((like_m.group(1).replace(',', '') if like_m else '0') or '0')


def get_content_chunk(detail_html: str) -> str:
    body_m = re.search(
        r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*\bview_content\b[^"\']*["\'][^>]*>',
        detail_html,
        re.I,
    )
    if not body_m:
        return detail_html

    depth = 1
    for token in re.finditer(r'<div\b[^>]*>|</div\s*>', detail_html[body_m.end():], re.I):
        if token.group(0).lower().startswith('</div'):
            depth -= 1
            if depth == 0:
                return detail_html[body_m.start():body_m.end() + token.end()]
        else:
            depth += 1
    return detail_html[body_m.start():]


def extract_buy_link(detail_html: str) -> str:
    # 본문 하단의 '출처: http...' 패턴을 최우선으로 사용
    chunk = get_content_chunk(detail_html)
    text_only = clean(re.sub(r'<[^>]+>', ' ', chunk))

    src_m = re.search(r'출처\s*[:：]\s*(https?://[^\s\"\'<>]+)', text_only, re.I)
    if src_m:
        return clean(src_m.group(1)).rstrip(').,;!?:')

    # HTML 상에 직접 텍스트로 박힌 경우도 보정
    src_m_html = re.search(r'출처\s*[:：]\s*(https?://[^\s\"\'<>]+)', chunk, re.I)
    if src_m_html:
        return clean(src_m_html.group(1)).rstrip(').,;!?:')

    # 출처 표기가 없으면 기존 외부 href 탐색 fallback
    for m in re.finditer(r'href="(https?://[^\"]+)"', chunk):
        link = clean(m.group(1))
        if 'ruliweb.com' in link:
            continue
        return link
    return ''


def extract_price_from_detail(detail_html: str) -> str:
    chunk = get_content_chunk(detail_html)
    text_only = clean(re.sub(r'<[^>]+>', ' ', chunk))
    return extract_best_price(text_only)


def _safe_style_classes(tag: str, attrs: dict) -> list[str]:
    style = str(attrs.get('style') or '')
    classes = []
    align_m = re.search(r'text-align\s*:\s*(center|right|justify)', style, re.I)
    align = (align_m.group(1).lower() if align_m else str(attrs.get('align') or '').lower())
    if align in {'center', 'right', 'justify'}:
        classes.append(f'gaji-align-{align}')

    font_size = None
    size_m = re.search(r'font-size\s*:\s*([0-9.]+)\s*(px|pt|em|rem|%)?', style, re.I)
    if size_m:
        value = float(size_m.group(1))
        unit = (size_m.group(2) or 'px').lower()
        font_size = {
            'px': value,
            'pt': value * 4 / 3,
            'em': value * 16,
            'rem': value * 16,
            '%': value * 0.16,
        }.get(unit, value)
    elif tag == 'font' and str(attrs.get('size') or '').strip().isdigit():
        legacy_size = int(attrs['size'])
        font_size = {1: 10, 2: 13, 3: 16, 4: 18, 5: 24, 6: 32, 7: 48}.get(legacy_size)

    if font_size is not None:
        if font_size >= 23:
            classes.append('gaji-text-xl')
        elif font_size >= 18:
            classes.append('gaji-text-lg')
        elif font_size <= 13:
            classes.append('gaji-text-sm')

    if re.search(r'font-weight\s*:\s*(?:bold|[6-9]00)', style, re.I):
        classes.append('gaji-font-bold')
    if re.search(r'text-decoration[^;]*\bunderline\b', style, re.I):
        classes.append('gaji-underline')
    return classes


class RuliwebRichBodyParser(HTMLParser):
    BLOCK_TAGS = {
        'p': 'p',
        'div': 'div',
        'center': 'div',
        'h1': 'h1',
        'h2': 'h2',
        'h3': 'h3',
        'h4': 'h3',
        'h5': 'h3',
        'h6': 'h3',
        'ul': 'ul',
        'ol': 'ol',
        'li': 'li',
        'blockquote': 'blockquote',
        'table': 'table',
        'thead': 'thead',
        'tbody': 'tbody',
        'tr': 'tr',
        'th': 'th',
        'td': 'td',
    }
    INLINE_TAGS = {
        'b': 'strong',
        'strong': 'strong',
        'i': 'em',
        'em': 'em',
    }
    DROP_CONTENT_TAGS = {'script', 'style', 'noscript', 'iframe', 'object', 'svg', 'canvas'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.open_tags = []
        self.drop_stack = []

    def _append_open(self, source_tag: str, output_tag: str, classes=None, attrs=None):
        attributes = []
        safe_classes = list(dict.fromkeys(classes or []))
        if safe_classes:
            attributes.append(f'class="{html.escape(" ".join(safe_classes), quote=True)}"')
        for key, value in (attrs or {}).items():
            attributes.append(f'{key}="{html.escape(str(value), quote=True)}"')
        suffix = f' {" ".join(attributes)}' if attributes else ''
        self.parts.append(f'<{output_tag}{suffix}>')
        self.open_tags.append((source_tag, output_tag))

    def _close_source_tag(self, source_tag: str):
        match_index = next(
            (idx for idx in range(len(self.open_tags) - 1, -1, -1) if self.open_tags[idx][0] == source_tag),
            None,
        )
        if match_index is None:
            return
        for _, output_tag in reversed(self.open_tags[match_index:]):
            if output_tag:
                self.parts.append(f'</{output_tag}>')
        del self.open_tags[match_index:]

    def handle_starttag(self, tag, attrs):
        tag = str(tag or '').lower()
        if self.drop_stack:
            self.drop_stack.append(tag)
            return
        if tag in self.DROP_CONTENT_TAGS:
            self.drop_stack.append(tag)
            return
        if tag in {'img', 'picture', 'source', 'video', 'audio'}:
            return
        if tag == 'br':
            self.parts.append('<br>')
            return
        if tag == 'hr':
            self.parts.append('<hr>')
            return

        attr_map = {str(key).lower(): value for key, value in attrs if key}
        classes = _safe_style_classes(tag, attr_map)
        if tag == 'center' and 'gaji-align-center' not in classes:
            classes.append('gaji-align-center')
        if tag == 'blockquote':
            classes.append('gaji-quote')
        if tag == 'table':
            classes.append('gaji-rich-table')

        if tag in self.BLOCK_TAGS:
            self._append_open(tag, self.BLOCK_TAGS[tag], classes)
            return
        if tag in self.INLINE_TAGS:
            self._append_open(tag, self.INLINE_TAGS[tag], classes)
            return
        if tag == 'u':
            self._append_open(tag, 'span', classes + ['gaji-underline'])
            return
        if tag in {'span', 'font'}:
            if classes:
                self._append_open(tag, 'span', classes)
            else:
                self.open_tags.append((tag, ''))
            return
        if tag == 'a':
            href = str(attr_map.get('href') or '').strip()
            if href.startswith('//'):
                href = f'https:{href}'
            elif href.startswith('/'):
                href = urljoin(BASE, href)
            parsed = urlparse(href)
            if parsed.scheme in {'http', 'https'}:
                self._append_open(
                    tag,
                    'a',
                    classes,
                    {'href': href, 'target': '_blank', 'rel': 'noopener noreferrer nofollow'},
                )
            else:
                self.open_tags.append((tag, ''))
            return
        self.open_tags.append((tag, ''))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if str(tag or '').lower() not in {'br', 'hr', 'img', 'picture', 'source', 'video', 'audio'}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = str(tag or '').lower()
        if self.drop_stack:
            if tag in self.drop_stack:
                while self.drop_stack:
                    opened = self.drop_stack.pop()
                    if opened == tag:
                        break
            return
        self._close_source_tag(tag)

    def handle_data(self, data):
        if self.drop_stack:
            return
        normalized = re.sub(r'\s+', ' ', str(data or ''))
        if normalized:
            self.parts.append(html.escape(normalized, quote=False))

    def safe_html(self) -> str:
        for _, output_tag in reversed(self.open_tags):
            if output_tag:
                self.parts.append(f'</{output_tag}>')
        self.open_tags.clear()
        return ''.join(self.parts).strip()


def extract_body_text(detail_html: str) -> str:
    chunk = get_content_chunk(detail_html)
    parser = RuliwebRichBodyParser()
    parser.feed(chunk)
    parser.close()
    rich_html = parser.safe_html()
    plain_text = clean(re.sub(r'<[^>]+>', ' ', rich_html))
    return f'{RICH_TEXT_PREFIX}{rich_html}' if plain_text else ''


def extract_primary_image(detail_html: str) -> str:
    # 루리웹은 상세 본문 첫 번째 이미지가 대표 이미지
    chunk = get_content_chunk(detail_html)
    for m in re.finditer(r'<img[^>]+(?:data-src|src)="([^"]+)"', chunk, re.I):
        src = clean(m.group(1))
        if not src:
            continue
        if src.startswith('//'):
            return f'https:{src}'
        if src.startswith('/'):
            return f'{BASE}{src}'
        return src

    # 일부 글은 view_content 정규식 누락될 수 있어 전체 문서에서 재탐색
    for m in re.finditer(r'<img[^>]+(?:data-src|src)="([^"]+)"', detail_html, re.I):
        src = clean(m.group(1))
        if not src:
            continue
        if src.startswith('//'):
            return f'https:{src}'
        if src.startswith('/'):
            return f'{BASE}{src}'
        return src
    return ''


def main():
    now = datetime.now(KST)
    since = now - timedelta(hours=48)
    previous_keys = build_previous_link_keys(load_previous_items())
    s = requests.Session()
    s.headers.update(HEADERS)

    filtered = []
    seen = set()

    for page in range(1, MAX_PAGES + 1):
        page_url = LIST_URL if page == 1 else f"{BASE}/market/board/1020?page={page}"
        page_html = s.get(page_url, timeout=25).text
        rows = parse_rows(page_html, seen)
        if not rows:
            continue

        older_streak = 0
        for row in rows:
            dt = parse_time_to_datetime(row.get('time', ''), now)
            if dt < since:
                older_streak += 1
                continue

            older_streak = 0
            try:
                detail_html = s.get(row['sourceLink'], timeout=25).text
                img_m = re.search(r'<meta property="og:image" content="([^"]*)"', detail_html)
                desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', detail_html)
                primary_img = extract_primary_image(detail_html)
                row['img'] = to_proxy_image_url(primary_img or (clean(img_m.group(1)) if img_m else ''))
                body_text = extract_body_text(detail_html)
                row['desc'] = body_text or (clean(desc_m.group(1)) if desc_m else '')
                detail_likes = parse_detail_like_count(detail_html)
                if detail_likes:
                    row['likes'] = detail_likes
                comment_quality = analyze_comment_quality(extract_comment_signal_text(detail_html))
                row['commentSignalScore'] = comment_quality['score']
                row['positiveCommentSignals'] = comment_quality['positiveCount']
                row['negativeCommentSignals'] = comment_quality['negativeCount']
                row['qualitySignalParserVersion'] = QUALITY_SIGNAL_PARSER_VERSION
                if row.get('price') in {'', '가격 정보 확인'}:
                    body_price = extract_price_from_detail(detail_html)
                    if body_price:
                        row['price'] = body_price
                    elif '무료' in (row.get('title') or '') or '무료' in (row.get('desc') or ''):
                        row['price'] = '무료'
                    elif '다양' in (row.get('title') or '') or '다양' in (row.get('desc') or ''):
                        row['price'] = '다양'
                row['buyLink'] = extract_buy_link(detail_html) or row['sourceLink']
            except Exception:
                row['buyLink'] = row['sourceLink']

            row['date'] = dt.strftime('%Y-%m-%d')
            row['registeredAt'] = dt.isoformat()
            filtered.append(row)

        # 최근 글부터 정렬되어 있으므로, 페이지 전체가 오래된 글이면 종료
        if older_streak >= len(rows):
            break
        if rows and page_tail_seen_in_previous(rows, previous_keys):
            print(f"RULIWEB_INCREMENTAL_STOP reason=page_tail_seen page={page} sample={max(1, INCREMENTAL_TAIL_SAMPLE_SIZE)}")
            break

    out = {
        "source": LIST_URL,
        "generatedAt": now.isoformat(),
        "rangeHours": 48,
        "since": since.isoformat(),
        "today": str(now.date()),
        "yesterday": str((now - timedelta(days=1)).date()),
        "counts": {"today": len(filtered), "yesterday": 0, "total": len(filtered)},
        "items": filtered,
        "grouped": {"today": filtered, "yesterday": []},
    }

    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"saved: {JSON_PATH} ({len(filtered)} items)")


if __name__ == '__main__':
    main()
