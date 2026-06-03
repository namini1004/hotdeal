#!/usr/bin/env python3
import base64
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
try:
    from hotdeal_quality_signals import analyze_comment_quality
except ModuleNotFoundError:
    from scripts.hotdeal_quality_signals import analyze_comment_quality

LIST_URL = "https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu"
BASE = "https://www.ppomppu.co.kr"
MAX_PAGES = 10
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "ppomppu_hotdeals_2days.json"
HIDDEN_PATH = ROOT / "assets" / "hidden_hotdeals.json"
THUMB_DIR = ROOT / "assets" / "ppomppu_thumbs"
KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.ppomppu.co.kr/"}


def pick(pattern: str, text: str) -> str:
    m = re.search(pattern, text)
    return html.unescape(m.group(1)).strip() if m else ""


def parse_int(value: str) -> int:
    value = re.sub(r'[^0-9]', '', value or '')
    return int(value) if value else 0


def parse_registered_at(detail: str):
    # Mobile pages expose the post date in .hi, while some views label it as "등록일".
    patterns = [
        r'<span class="hi">\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*</span>',
        r'등록일\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})',
    ]
    for pattern in patterns:
        m = re.search(pattern, detail)
        if not m:
            continue
        try:
            return datetime.strptime(m.group(1), '%Y-%m-%d %H:%M').replace(tzinfo=KST)
        except ValueError:
            pass

    ts_m = re.search(r'G_BBS_REG_DATE\s*=\s*"(\d+)"', detail)
    if ts_m:
        ts = int(ts_m.group(1))
        if ts > 1000000000:
            return datetime.fromtimestamp(ts, tz=KST)
    return None


def parse_recommend_counts(detail: str) -> tuple[int, int]:
    recommend_m = re.search(r'<[^>]+id=["\']recommend["\'][^>]*>([\s\S]*?)(?:</div>|</section>)', detail, re.I)
    scope = recommend_m.group(1) if recommend_m else detail
    up_m = re.search(r'class=["\'][^"\']*up-numb[^"\']*["\'][^>]*>\s*([0-9,]+)\s*<', scope, re.I)
    down_m = re.search(r'class=["\'][^"\']*down-numb[^"\']*["\'][^>]*>\s*([0-9,]+)\s*<', scope, re.I)
    return parse_int(up_m.group(1) if up_m else ''), parse_int(down_m.group(1) if down_m else '')


def parse_post_stats(detail: str) -> tuple[int, int]:
    views = 0
    for p in [
        r'조회\s*:\s*([0-9,]+)',
        r'조회수\s*[:：]\s*([0-9,]+)',
        r'"view_count"\s*:\s*"?([0-9,]+)"?',
    ]:
        m = re.search(p, detail)
        if m:
            views = parse_int(m.group(1))
            break

    comments = 0
    for p in [
        r'<span class="list_comment">\s*([0-9,]+)\s*</span>',
        r'댓글\s*[:：]\s*([0-9,]+)',
        r'코멘트\s*[:：]\s*([0-9,]+)',
        r'"comment_count"\s*:\s*"?([0-9,]+)"?',
    ]:
        m = re.search(p, detail)
        if m:
            comments = parse_int(m.group(1))
            break
    return views, comments


def extract_body_chunk(detail: str) -> str:
    # 모바일 본문은 id=KH_Content 영역에 들어간다. 중첩 div 때문에 단순 non-greedy div 매칭 대신
    # 본문 시작점부터 하단 추천/댓글 영역 전까지 잘라 쓴다.
    start_m = re.search(r'<div[^>]+id=["\']KH_Content["\'][^>]*>', detail, re.I)
    if not start_m:
        body_m = re.search(r'<div[^>]+class=["\'][^"\']*cont[^"\']*["\'][^>]*>[\s\S]*?</div>', detail, re.I)
        return body_m.group(0) if body_m else detail

    chunk = detail[start_m.start():]
    end_m = re.search(
        r'<(?:div|section|ul)[^>]+(?:class|id)=["\'][^"\']*(?:bbs_view_bottom|comment|reply|recommend|bottom_btn)[^"\']*["\']',
        chunk,
        re.I,
    )
    return chunk[:end_m.start()] if end_m else chunk


def normalize_image_url(src: str) -> str:
    src = html.unescape(src or '').strip()
    if not src:
        return ''
    if src.startswith('//'):
        return normalize_ppomppu_cdn_host('https:' + src)
    normalized = urljoin(BASE, src)
    return normalize_ppomppu_cdn_host(normalized)


def normalize_ppomppu_cdn_host(src: str) -> str:
    """cdn2 이미지는 브라우저에서 실패하는 케이스가 있어 같은 경로의 cdn3로 저장한다."""
    return re.sub(r'^https://cdn2\.ppomppu\.co\.kr/', 'https://cdn3.ppomppu.co.kr/', src or '', flags=re.I)


def is_body_image_candidate(src: str) -> bool:
    src_l = (src or '').lower()
    if not src_l.startswith('http'):
        return False
    blocked = [
        'logo',
        'blank.',
        'transparent.',
        'noimage',
        'no_image',
        'btn_',
        'icon',
        'emoticon',
        'avatar',
        'profile',
        '/images/main/',
        '/images/menu/',
        '/images/common/',
    ]
    return not any(token in src_l for token in blocked)


def extract_body_image(detail: str) -> str:
    """뽐딜 대표 이미지는 og:image/목록 이미지보다 본문(KH_Content)의 첫 실제 이미지를 우선한다."""
    chunk = extract_body_chunk(detail)
    chunk = re.sub(r'<script[\s\S]*?</script>', ' ', chunk, flags=re.I)
    chunk = re.sub(r'<style[\s\S]*?</style>', ' ', chunk, flags=re.I)
    for img_m in re.finditer(r'<img\b[^>]*>', chunk, re.I):
        tag = img_m.group(0)
        src_m = re.search(r'(?:data-original|data-src|src)=["\']([^"\']+)', tag, re.I)
        if not src_m:
            continue
        candidate = normalize_image_url(src_m.group(1))
        if is_body_image_candidate(candidate):
            return candidate
    return ''


def extract_body_text(detail: str) -> str:
    chunk = extract_body_chunk(detail)

    # 본문에 섞여 들어오는 script/style 제거
    chunk = re.sub(r'<script[\s\S]*?</script>', ' ', chunk, flags=re.I)
    chunk = re.sub(r'<style[\s\S]*?</style>', ' ', chunk, flags=re.I)

    text = re.sub(r'<br\s*/?>', '\n', chunk, flags=re.I)
    text = re.sub(r'</p\s*>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\r\n?', '\n', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.strip()

    # 요청 케이스: '유효기간 1년입니다'부터 '변경하여 사용할 수 있습니다' 구간만 사용
    start_token = '유효기간 1년입니다'
    end_token = '변경하여 사용할 수 있습니다'
    s_idx = text.find(start_token)
    e_idx = text.find(end_token)
    if s_idx != -1 and e_idx != -1 and e_idx >= s_idx:
        text = text[s_idx:e_idx + len(end_token)].strip()

    return text


def load_hidden_hotdeals():
    if not HIDDEN_PATH.exists():
        return {"sourceLinks": set(), "bbsNos": set()}
    try:
        data = json.loads(HIDDEN_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {"sourceLinks": set(), "bbsNos": set()}

    return {
        "sourceLinks": set(data.get("sourceLinks", [])),
        "bbsNos": {str(v) for v in data.get("bbsNos", [])},
    }


def bbs_no_from_url(url: str) -> str:
    q = parse_qs(urlparse(url).query)
    return (q.get("no", [""])[0] or "").strip()


def load_previous_items():
    if not JSON_PATH.exists():
        return []
    try:
        data = json.loads(JSON_PATH.read_text(encoding='utf-8'))
        return list(data.get('items') or [])
    except Exception:
        return []


def has_reusable_detail_fields(item: dict) -> bool:
    return bool(
        (item.get('title') or '').strip()
        and (item.get('registeredAt') or '').strip()
        and (item.get('desc') or '').strip()
    )


def build_previous_detail_lookup(items):
    lookup = {}
    for item in items or []:
        if not has_reusable_detail_fields(item):
            continue
        source_link = (item.get('sourceLink') or '').strip()
        no = bbs_no_from_url(source_link)
        if no:
            lookup[f'no:{no}'] = item
        if source_link:
            lookup[f'source:{source_link}'] = item
    return lookup


def apply_cached_detail_fields(row: dict, lookup: dict) -> bool:
    href = row.get('href') or ''
    cached = lookup.get(f"no:{bbs_no_from_url(href)}") or lookup.get(f"source:{href}")
    if not cached or not has_reusable_detail_fields(cached):
        return False
    for key in (
        'title', 'registeredAt', 'date', 'time', 'price', 'likes', 'dislikes',
        'views', 'comments', 'commentSignalScore', 'positiveCommentSignals',
        'negativeCommentSignals', 'desc', 'img', 'buyLink'
    ):
        value = cached.get(key)
        if value not in (None, ''):
            row[key] = value
    row['_detailCached'] = True
    return True


def strip_tags(value: str) -> str:
    value = re.sub(r'<[^>]+>', '', value or '')
    return html.unescape(value).strip()


def canonicalize_source_link(url: str) -> str:
    parsed = urlparse(urljoin(LIST_URL, html.unescape(url or '').replace('&&', '&')))
    query = parse_qs(parsed.query)
    no = (query.get('no') or [''])[0]
    board_id = (query.get('id') or ['ppomppu'])[0]
    if no:
        canonical_query = urlencode({'id': board_id or 'ppomppu', 'no': no})
        return f'{parsed.scheme}://{parsed.netloc}{parsed.path}?{canonical_query}'
    return parsed.geturl()


def parse_list_rows(list_html: str):
    rows = []

    desktop_blocks = re.findall(
        r'<tr[^>]*class=["\'][^"\']*baseList[^"\']*["\'][^>]*>[\s\S]*?</tr>',
        list_html,
        re.I,
    )
    for b in desktop_blocks:
        href_m = re.search(
            r'<a[^>]+class=["\'][^"\']*baseList-title[^"\']*["\'][^>]+href=["\']([^"\']+)',
            b,
            re.I,
        )
        title_m = re.search(
            r'<a[^>]+class=["\'][^"\']*baseList-title[^"\']*["\'][^>]*>([\s\S]*?)</a>',
            b,
            re.I,
        )
        if not href_m or not title_m:
            continue

        href = canonicalize_source_link(href_m.group(1))
        if parse_qs(urlparse(href).query).get('id', [''])[0] != 'ppomppu':
            continue
        raw_title = strip_tags(title_m.group(1))
        img = ''
        img_m = re.search(r'<a[^>]+class=["\'][^"\']*baseList-thumb[^"\']*["\'][\s\S]*?<img[^>]+src=["\']([^"\']+)', b, re.I)
        if img_m:
            img = normalize_image_url(img_m.group(1))
        category_m = re.match(r'\[([^\]]+)\]', raw_title)
        category = category_m.group(1).strip() if category_m else '기타'
        comments_m = re.search(r'class=["\'][^"\']*baseList-c[^"\']*["\'][^>]*>\s*([0-9,]+)\s*<', b, re.I)
        likes_m = re.search(r'class=["\'][^"\']*baseList-rec[^"\']*["\'][^>]*>\s*([0-9,]*)\s*</td>', b, re.I)
        views_m = re.search(r'class=["\'][^"\']*baseList-views[^"\']*["\'][^>]*>\s*([0-9,]*)\s*</td>', b, re.I)
        rows.append({
            "href": href,
            "raw_title": raw_title,
            "img": img,
            "category": category,
            "views": parse_int(views_m.group(1) if views_m else ''),
            "comments": parse_int(comments_m.group(1) if comments_m else ''),
            "likes": parse_int(likes_m.group(1) if likes_m else ''),
        })

    if rows:
        return rows

    mobile_blocks = re.findall(r'<li class="none-border bbs_list_thumbnail new_sk "[\s\S]*?</li>', list_html)
    for b in mobile_blocks:
        href_m = re.search(r'<a href="([^"]*bbs_view\.php[^"]+)"', b)
        title_m = re.search(r'<span class="cont"[^>]*>([\s\S]*?)</span>', b)
        img_m = re.search(r'<img src="([^"]+)"', b)
        cat_m = re.search(r'<li class="names">\[([^\]]+)\]', b)
        if not href_m or not title_m:
            continue
        img = normalize_image_url(img_m.group(1)) if img_m else ''
        rows.append({
            "href": canonicalize_source_link(href_m.group(1)),
            "raw_title": strip_tags(title_m.group(1)),
            "img": img,
            "category": cat_m.group(1).strip() if cat_m else "기타",
            "views": 0,
            "comments": 0,
            "likes": 0,
        })
    return rows


def parse_items():
    s = requests.Session()
    s.headers.update(HEADERS)
    previous_lookup = build_previous_detail_lookup(load_previous_items())

    # 페이지를 순회해서(더보기 포함) 링크를 충분히 수집
    link_rows = []
    seen_links = set()
    for page in range(1, MAX_PAGES + 1):
        page_url = LIST_URL if page == 1 else f"{LIST_URL}&page={page}"
        list_html = s.get(page_url, timeout=20).text
        rows = parse_list_rows(list_html)
        if not rows:
            break

        new_in_page = 0
        for row in rows:
            href = row["href"]
            if href in seen_links:
                continue
            seen_links.add(href)
            new_in_page += 1
            link_rows.append(row)

        if new_in_page == 0:
            break

    items = []
    for row in link_rows:
        href = row['href']
        raw_title = row['raw_title']
        img = row['img']
        category = row['category']

        if apply_cached_detail_fields(row, previous_lookup):
            items.append({
                "id": str(len(items) + 1),
                "title": row.get('title') or raw_title,
                "area": "뽐뿌 핫딜",
                "dist": category,
                "time": row.get('date') or '',
                "registeredAt": row.get('registeredAt') or '',
                "price": row.get('price') or '',
                "likes": int(row.get('likes') or 0),
                "dislikes": int(row.get('dislikes') or 0),
                "views": int(row.get('views') or 0),
                "comments": int(row.get('comments') or 0),
                "commentSignalScore": int(row.get('commentSignalScore') or 0),
                "positiveCommentSignals": int(row.get('positiveCommentSignals') or 0),
                "negativeCommentSignals": int(row.get('negativeCommentSignals') or 0),
                "category": category,
                "desc": row.get('desc') or '',
                "img": row.get('img') or img,
                "buyLink": row.get('buyLink') or '',
                "sourceLink": href,
                "source": "ppomppu",
                "date": row.get('date') or '',
            })
            continue

        detail = s.get(href, timeout=20).text
        og_title = pick(r'<meta property="og:title" content="([^"]*)"', detail) or raw_title
        og_desc = pick(r'<meta property="og:description" content="([^"]*)"', detail)
        body_desc = extract_body_text(detail)
        og_img = pick(r'<meta property="og:image" content="([^"]*)"', detail) or img
        og_img = normalize_ppomppu_cdn_host(og_img)
        body_img = extract_body_image(detail)
        representative_img = body_img or og_img

        dt = parse_registered_at(detail)
        date_label = dt.strftime('%Y-%m-%d') if dt else ""
        registered_at = dt.isoformat() if dt else ""
        views, comments = parse_post_stats(detail)
        if not views:
            views = row.get('views', 0)
        if not comments:
            comments = row.get('comments', 0)
        recommend_up, recommend_down = parse_recommend_counts(detail)
        comment_quality = analyze_comment_quality(detail)

        # 사러가기 URL (상단 닉네임 아래 링크의 실제 target)
        buy_link = ""
        s_m = re.search(r'(?:href=["\'])?(https://s\.ppomppu\.co\.kr\?[^"\'<>\s]+)', detail)
        if s_m:
            s_url = html.unescape(s_m.group(1))
            q = parse_qs(urlparse(s_url).query)
            target = q.get('target', [''])[0]
            if target:
                try:
                    buy_link = base64.b64decode(target + '===').decode('utf-8', 'ignore')
                except Exception:
                    pass

        pm = re.search(r'\(([0-9,]+원)\s*/\s*([^\)]+)\)', og_title)
        price = pm.group(1) if pm else ""
        if not price:
            title_price_m = re.search(r'([0-9][0-9,]*원)', og_title)
            if title_price_m:
                price = title_price_m.group(1)
        if not price:
            price = ""

        items.append({
            "id": str(len(items) + 1),
            "title": og_title,
            "area": "뽐뿌 핫딜",
            "dist": category,
            "time": date_label,
            "registeredAt": registered_at,
            "price": price,
            "likes": recommend_up or row.get('likes', 0),
            "dislikes": recommend_down,
            "views": views,
            "comments": comments,
            "commentSignalScore": comment_quality['score'],
            "positiveCommentSignals": comment_quality['positiveCount'],
            "negativeCommentSignals": comment_quality['negativeCount'],
            "category": category,
            "desc": body_desc or og_desc or "",
            "img": representative_img,
            "buyLink": buy_link,
            "sourceLink": href,
            "source": "ppomppu",
            "date": date_label,
        })

    now = datetime.now(KST)
    since = now - timedelta(hours=48)

    hidden = load_hidden_hotdeals()
    filtered = [
        it for it in items
        if it.get('registeredAt')
        and datetime.fromisoformat(it['registeredAt']) >= since
        and it.get('sourceLink') not in hidden["sourceLinks"]
        and bbs_no_from_url(it.get('sourceLink', '')) not in hidden["bbsNos"]
    ]
    for i, it in enumerate(filtered, 1):
        it['id'] = str(i)

    grouped = {"today": filtered, "yesterday": []}

    out = {
        "source": LIST_URL,
        "generatedAt": now.isoformat(),
        "rangeHours": 48,
        "since": since.isoformat(),
        "today": str(now.date()),
        "yesterday": str((now - timedelta(days=1)).date()),
        "counts": {
            "today": len(filtered),
            "yesterday": 0,
            "total": len(filtered),
        },
        "items": filtered,
        "grouped": grouped,
    }
    return out


def cache_thumbnails(data):
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update(HEADERS)

    def ext_from_ct(ct):
        if not ct:
            return '.jpg'
        ct = ct.lower()
        if 'png' in ct:
            return '.png'
        if 'webp' in ct:
            return '.webp'
        if 'gif' in ct:
            return '.gif'
        return '.jpg'

    src_map = {}
    for it in data.get('items', []):
        src = it.get('img', '')
        m = re.search(r'no=(\d+)', it.get('sourceLink', ''))
        nid = m.group(1) if m else it.get('id', 'x')

        local_rel = ''
        existing_rel = ''
        for ext in ['.jpg', '.png', '.webp', '.gif']:
            p = THUMB_DIR / f'{nid}{ext}'
            if p.exists():
                existing_rel = f'assets/ppomppu_thumbs/{nid}{ext}'
                break

        # 본문 첫 이미지 추출 로직이 바뀐 뒤 기존 og/list 썸네일 캐시가 남아 있으면
        # 계속 오래된 이미지가 보이므로, 원격 본문 이미지가 있으면 우선 재다운로드한다.
        if src.startswith('http'):
            try:
                r = s.get(src, timeout=15)
                if r.status_code == 200 and len(r.content) > 500:
                    ext = ext_from_ct(r.headers.get('content-type', ''))
                    p = THUMB_DIR / f'{nid}{ext}'
                    p.write_bytes(r.content)
                    local_rel = f'assets/ppomppu_thumbs/{nid}{ext}'
            except Exception:
                pass

        if not local_rel:
            local_rel = existing_rel
        if local_rel:
            it['img'] = local_rel
        src_map[it.get('sourceLink')] = it

    for key in ['today', 'yesterday']:
        new_list = []
        for it in data.get('grouped', {}).get(key, []):
            new_list.append(src_map.get(it.get('sourceLink'), it))
        data['grouped'][key] = new_list


def main():
    new_data = parse_items()
    # Supabase/GitHub Actions 운영에서는 15분마다 웹 배포를 하지 않으므로 새 로컬 썸네일 경로를
    # JSON에 쓰면 운영 화면에서 파일이 없을 수 있다. 기본은 본문 원격 이미지 URL을 유지하고,
    # 정적 배포용 로컬 캐시가 필요할 때만 CACHE_PPOMPPU_THUMBS=1로 켠다.
    if (os.environ.get('CACHE_PPOMPPU_THUMBS') or '').strip() == '1':
        cache_thumbnails(new_data)

    old = None
    if JSON_PATH.exists():
        old = JSON_PATH.read_text(encoding='utf-8')

    new_text = json.dumps(new_data, ensure_ascii=False, indent=2)
    if old == new_text:
        print('NO_CHANGE')
        return

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(new_text, encoding='utf-8')
    print(f"UPDATED total={new_data['counts']['total']} today={new_data['counts']['today']} yesterday={new_data['counts']['yesterday']}")


if __name__ == '__main__':
    main()
