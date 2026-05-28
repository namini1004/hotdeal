#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

LIST_URL = "https://quasarzone.com/bbs/qb_saleinfo"
BASE = "https://quasarzone.com"
MAX_PAGES = 8
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "quasar_hotdeals_2days.json"
KST = timezone(timedelta(hours=9))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Referer": "https://quasarzone.com/bbs/qb_saleinfo",
}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def parse_time_to_datetime(time_text: str, now: datetime) -> datetime:
    text = (time_text or "").strip()
    if text in {"방금", "조금 전"}:
        return now

    minute_m = re.search(r"(\d+)\s*분 전", text)
    if minute_m:
        return now - timedelta(minutes=int(minute_m.group(1)))

    hour_m = re.search(r"(\d+)\s*시간 전", text)
    if hour_m:
        return now - timedelta(hours=int(hour_m.group(1)))

    m = re.search(r"(\d{2})-(\d{2})", text)
    if m:
        mm, dd = int(m.group(1)), int(m.group(2))
        year = now.year
        # 연초 경계 처리
        if now.month == 1 and mm == 12:
            year -= 1
        return datetime(year, mm, dd, 0, 0, tzinfo=KST)

    return now


def parse_time_to_date_label(time_text: str, now: datetime) -> str:
    return parse_time_to_datetime(time_text, now).strftime("%Y-%m-%d")


def to_jina_url(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or '/'
    query = f'?{parsed.query}' if parsed.query else ''
    return f"https://r.jina.ai/http://{parsed.netloc}{path}{query}"


def clean_price(price: str) -> str:
    price = clean(price)
    if '(KRW)' in price:
        num_m = re.search(r'([0-9][0-9,]*)\s*\(KRW\)', price, re.I)
        if num_m:
            price = f"{num_m.group(1)}원"
        else:
            price = price.replace('(KRW)', '원').replace(' KRW', '원')
    price = price.replace('￦', '').replace('₩', '').strip()
    price = re.sub(r'\s+', ' ', price)
    price = re.sub(r'\s*원\s*원$', '원', price)
    return price


def normalize_source_link(raw_link: str) -> str:
    absolute = urljoin(BASE, html.unescape(raw_link or ""))
    parsed = urlsplit(absolute)
    # 목록 page/query가 상세 URL에 붙어 있어도 동일 게시글로 canonicalize 한다.
    scheme = 'https' if parsed.netloc.endswith('quasarzone.com') else parsed.scheme
    return f"{scheme}://{parsed.netloc}{parsed.path}"


def normalize_image_url(src: str) -> str:
    src = html.unescape(src or '').strip()
    if not src:
        return ''
    if src.startswith('//'):
        return 'https:' + src
    return urljoin(BASE, src)


def is_body_image_candidate(src: str) -> bool:
    src_l = (src or '').lower()
    if not src_l.startswith('http'):
        return False
    blocked = [
        'thumb_no_image',
        'no_image',
        '/assets/images/',
        '/level/',
        '/store/',
        'emoticon',
        'avatar',
        'profile',
        'blank.',
        'transparent.',
    ]
    return not any(token in src_l for token in blocked)


def get_img_src_from_tag(tag: str) -> str:
    """lazy 이미지에서 placeholder src보다 실제 data-* 원본을 우선한다."""
    for attr in ("data-src", "data-original", "data-url", "src"):
        m = re.search(rf'\b{attr}=[\"\']([^\"\']+)', tag, re.I)
        if m:
            candidate = normalize_image_url(m.group(1))
            if is_body_image_candidate(candidate):
                return candidate

    srcset_m = re.search(r'\bsrcset=[\"\']([^\"\']+)', tag, re.I)
    if srcset_m:
        for part in srcset_m.group(1).split(','):
            candidate = normalize_image_url(part.strip().split()[0] if part.strip() else '')
            if is_body_image_candidate(candidate):
                return candidate

    return ''


def iter_detail_body_html(detail_html: str):
    """퀘이사 상세에서 가격/배송 표 이후의 실제 본문 영역 후보만 순서대로 반환한다."""
    # 1) 원본 HTML: 가격/배송 메타 뒤 실제 본문은 textarea#org_contents 안에 보관된다.
    for body_m in re.finditer(r'<textarea[^>]*\bid=[\"\']org_contents[\"\'][^>]*>([\s\S]*?)</textarea>', detail_html, re.I):
        yield html.unescape(body_m.group(1))

    # 2) 일부 렌더/개편 케이스: 본문 컨테이너 후보. 상단 판매처 로고/프로필 영역은 제외한다.
    container_patterns = [
        r'<div[^>]*\bclass=[\"\'][^\"\']*(?:board-view-content|view-content|content-detail|fr-view|se-viewer)[^\"\']*[\"\'][^>]*>([\s\S]*?)</div>\s*</div>',
        r'<article[^>]*>([\s\S]*?)</article>',
    ]
    for pattern in container_patterns:
        for body_m in re.finditer(pattern, detail_html, re.I):
            yield html.unescape(body_m.group(1))


def extract_body_image_from_detail(detail_html: str) -> str:
    """퀘딜 대표 이미지는 목록 썸네일/상단 판매처 로고가 아니라 가격/배송비 뒤 본문 첫 이미지로 고정한다."""
    for body_html in iter_detail_body_html(detail_html):
        for img_m in re.finditer(r'<img\b[^>]*>', body_html, re.I):
            candidate = get_img_src_from_tag(img_m.group(0))
            if candidate:
                return candidate

    # r.jina.ai markdown fallback: 링크/판매처/가격/배송 표 이후 본문에서 첫 markdown 이미지를 고른다.
    marker = re.search(r'\|\s*배송(?:비/직배)?[^\n]*\n', detail_html, re.I)
    body_text = detail_html[marker.end():] if marker else detail_html
    for md_m in re.finditer(r'!\[[^\]]*\]\((https?://[^\)\s]+)', body_text):
        candidate = normalize_image_url(md_m.group(1))
        if is_body_image_candidate(candidate):
            return candidate

    return ''


def extract_buy_link_from_detail(detail_html: str) -> str:
    # 0) r.jina.ai 마크다운 렌더: 상세 표의 링크 행
    m = re.search(r'\|\s*링크[\s\S]*?\|\s*\[(https?://[^\]\s]+)\]\(', detail_html, re.I)
    if m:
        return html.unescape(m.group(1)).strip()

    # 1) 퀘이사 본문 우측 링크 버튼이 이 함수의 url 변수로 내려오는 경우가 많음
    m = re.search(
        r'function\s+contentLinkPrice\(\)\s*\{[\s\S]*?var\s+url\s*=\s*[\'\"]([^\'\"]+)',
        detail_html,
        re.I,
    )
    if m:
        candidate = html.unescape(m.group(1)).strip()
        if candidate.startswith('http'):
            return candidate

    # 2) 본문 원문(textarea#org_contents) 안의 링크 추출
    body_m = re.search(r'<textarea[^>]*id="org_contents"[^>]*>([\s\S]*?)</textarea>', detail_html, re.I)
    if body_m:
        body_html = html.unescape(body_m.group(1))
        for hm in re.finditer(r'href=[\"\'](https?://[^\"\']+)', body_html, re.I):
            link = html.unescape(hm.group(1)).strip()
            if 'img2.quasarzone.com' in link:
                continue
            return link
        for tm in re.finditer(r'(https?://[^\s\"\'<>]+)', body_html, re.I):
            link = html.unescape(tm.group(1)).strip()
            if 'img2.quasarzone.com' in link:
                continue
            return link

    # 3) 메타 설명 URL(축약 URL 제외)
    og_desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', detail_html)
    if og_desc_m:
        desc = html.unescape(og_desc_m.group(1))
        url_m = re.search(r'(https?://[^\s\]\)"\']+)', desc)
        if url_m:
            candidate = url_m.group(1).strip()
            if '…' not in candidate and '...' not in candidate:
                return candidate

    return ''


def extract_body_text_from_detail(detail_html: str) -> str:
    md_body_m = re.search(r'\|\s*배송비/직배[\s\S]*?\|[^\n]*\n\n([\s\S]*?)\n\n\[\]\(http', detail_html, re.I)
    if md_body_m:
        text = re.sub(r'!\[[^\]]*\]\([^\)]*\)', ' ', md_body_m.group(1))
        text = re.sub(r'\[([^\]]+)\]\([^\)]*\)', r'\1', text)
        return clean(text)

    body_m = re.search(r'<textarea[^>]*id="org_contents"[^>]*>([\s\S]*?)</textarea>', detail_html, re.I)
    if body_m:
        body_html = html.unescape(body_m.group(1))
        text = re.sub(r'<br\s*/?>', '\n', body_html, flags=re.I)
        text = re.sub(r'</p\s*>', '\n', text, flags=re.I)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        text = re.sub(r'\r\n?', '\n', text)
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    og_desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', detail_html)
    return html.unescape(og_desc_m.group(1)).strip() if og_desc_m else ''


def extract_registered_at_from_detail(detail_html: str, fallback_date_label: str) -> str:
    patterns = [
        r'(20\d{2})[./-](\d{2})[./-](\d{2})\s+(\d{2}):(\d{2})',
        r'(20\d{2})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2})(?::\d{2})?',
    ]
    for p in patterns:
        m = re.search(p, detail_html)
        if not m:
            continue
        try:
            y, mm, dd, hh, mi = map(int, m.groups()[:5])
            return datetime(y, mm, dd, hh, mi, tzinfo=KST).isoformat()
        except Exception:
            pass

    return f"{fallback_date_label}T00:00:00+09:00"


def parse_list_items(page_html: str, seen=None):
    rows = re.findall(r"<tr>[\s\S]*?<\/tr>", page_html)
    items = []
    if seen is None:
        seen = set()

    for row in rows:
        link_m = re.search(r'href="(/bbs/qb_saleinfo/views/(\d+)(?:\?[^\"]*)?)"', row)
        if not link_m:
            continue

        rel_link, post_id = link_m.group(1), link_m.group(2)
        if post_id in seen:
            continue
        seen.add(post_id)

        title_m = re.search(r'class="subject-link[^\"]*"[^>]*>\s*([\s\S]*?)\s*</a>', row)
        if not title_m:
            continue
        raw_title_html = re.sub(r'<span class="board-list-comment">[\s\S]*?</span>', '', title_m.group(1))
        raw_title = re.sub(r"<[^>]+>", "", raw_title_html)
        title = clean(raw_title)

        if "공지" in row[:400] or "핫딜 게시판 규정" in title:
            continue

        category_m = re.search(r'<span class="category">([\s\S]*?)</span>', row)
        category = clean(category_m.group(1)) if category_m else "기타"

        price_m = re.search(r'<span class="text-orange">([\s\S]*?)</span>', row)
        price = clean_price(price_m.group(1)) if price_m else "가격 정보 확인"

        comments_m = re.search(r'class="ctn-count\s*">\s*([0-9,]+)\s*</span>', row)
        comments = int((comments_m.group(1).replace(',', '') if comments_m else '0') or '0')

        count_matches = re.findall(r'<span class="count">\s*([0-9.,kK]+)\s*</span>', row)
        likes_text = count_matches[0] if len(count_matches) >= 2 else '0'
        views_text = count_matches[-1] if count_matches else '0'

        l = likes_text.lower().replace(',', '').strip()
        if l.endswith('k'):
            try:
                likes = int(float(l[:-1]) * 1000)
            except Exception:
                likes = 0
        else:
            try:
                likes = int(float(l))
            except Exception:
                likes = 0

        v = views_text.lower().replace(',', '').strip()
        if v.endswith('k'):
            try:
                views = int(float(v[:-1]) * 1000)
            except Exception:
                views = 0
        else:
            try:
                views = int(float(v))
            except Exception:
                views = 0

        date_m = re.search(r'<span class="date">\s*([\s\S]*?)\s*</span>', row)
        time_text = clean(date_m.group(1)) if date_m else ''

        img_m = re.search(r'<img[^>]+class="maxImg"[^>]+src="([^"]+)"', row)
        img = clean(img_m.group(1)) if img_m else ''

        items.append(
            {
                "id": post_id,
                "title": title or "제목 없음",
                "area": "퀘이사딜",
                "dist": category,
                "time": time_text,
                "price": price,
                "likes": likes,
                "views": views,
                "comments": comments,
                "category": category,
                "desc": "",
                "img": img,
                "buyLink": "",
                "sourceLink": normalize_source_link(rel_link),
                "source": "quasar",
            }
        )

    return items


def parse_jina_list_items(markdown_text: str, seen=None):
    items = []
    if seen is None:
        seen = set()

    # r.jina.ai 렌더는 표 한 줄에 썸네일 링크 + 제목 링크 + 메타를 평탄화해 준다.
    for line in (markdown_text or '').splitlines():
        if '/bbs/qb_saleinfo/views/' not in line or '가격' not in line:
            continue
        title_m = re.search(
            r'(?:진행중|인기)\[(.*?)\]\((https?://(?:www\.)?quasarzone\.com/bbs/qb_saleinfo/views/(\d+)(?:\?[^\)]*)?)\)',
            line,
        )
        if not title_m:
            continue

        raw_title, href, post_id = title_m.group(1), title_m.group(2), title_m.group(3)
        if post_id in seen or post_id == '1948168':
            continue
        seen.add(post_id)

        title = clean(re.sub(r'^진행중\s*', '', raw_title))
        trailing_comment_m = re.search(r'^(\[[^\]]+\].*?)(\d{1,3})$', title)
        if trailing_comment_m:
            title = trailing_comment_m.group(1).strip()
            comments = int(trailing_comment_m.group(2))
        else:
            comments = 0
        comment_m = re.search(r'\s+([0-9,]+)$', title)
        if comment_m:
            comments = int(comment_m.group(1).replace(',', ''))
            title = title[:comment_m.start()].strip()

        after = line[line.find(f']({href})') + len(f']({href})'):]
        category_m = re.search(r'\)\s*([^\s|]+)\s+가격\s+', line)
        category = clean(category_m.group(1)) if category_m else '기타'
        price_m = re.search(r'가격\s+([^|!]+?)(?:배송비|\!\[|\s{2,}|$)', after)
        price = clean_price(price_m.group(1)) if price_m else '가격 정보 확인'

        img_candidates = re.findall(r'!\[[^\]]*\]\((https?://[^\)]+)\)', line)
        img = ''
        for src in img_candidates:
            if 'thumb_no_image.svg' in src or '/level/' in src or '/store/' in src:
                continue
            img = clean(src)
            break

        tail_m = re.search(r'\s([0-9.,]+k?)\s+(방금|조금 전|\d+분 전|\d+시간 전|\d{2}-\d{2})\s*\|?\s*$', line)
        views_text = tail_m.group(1) if tail_m else '0'
        time_text = tail_m.group(2) if tail_m else ''
        v = views_text.lower().replace(',', '').strip()
        try:
            views = int(float(v[:-1]) * 1000) if v.endswith('k') else int(float(v))
        except Exception:
            views = 0

        items.append(
            {
                "id": post_id,
                "title": title or "제목 없음",
                "area": "퀘이사딜",
                "dist": category,
                "time": time_text,
                "price": price,
                "likes": 0,
                "views": views,
                "comments": comments,
                "category": category,
                "desc": "",
                "img": img,
                "buyLink": "",
                "sourceLink": normalize_source_link(href),
                "source": "quasar",
                "_detailViaJina": True,
            }
        )

    return items


def main():
    now = datetime.now(KST)
    since = now - timedelta(hours=48)
    sess = requests.Session()
    sess.headers.update(HEADERS)

    filtered = []
    seen = set()

    for page in range(1, MAX_PAGES + 1):
        page_url = LIST_URL if page == 1 else f"{LIST_URL}?page={page}"
        html_text = sess.get(page_url, timeout=25).text
        rows = parse_list_items(html_text, seen)
        if not rows:
            jina_text = sess.get(to_jina_url(page_url), timeout=45).text
            rows = parse_jina_list_items(jina_text, seen)
        if not rows:
            continue

        old_count = 0
        for row in rows:
            dt = parse_time_to_datetime(row.get("time", ""), now)
            date_label = parse_time_to_date_label(row.get("time", ""), now)
            # MM-DD만 있는 경계일은 상세 작성시각을 봐야 48시간 포함 여부를 정확히 알 수 있다.
            if dt < since and dt.date() != since.date():
                old_count += 1
                continue

            # 사이트별 룰: 상세에서 실제 구매처 링크/작성시각 추출
            detail_html = ""
            try:
                if row.get("_detailViaJina"):
                    detail_html = sess.get(to_jina_url(row["sourceLink"]), timeout=25).text
                else:
                    detail_html = sess.get(row["sourceLink"], timeout=25).text
                    if not extract_buy_link_from_detail(detail_html) and not re.search(r'20\d{2}[./-]\d{2}[./-]\d{2}\s+\d{2}:\d{2}', detail_html):
                        detail_html = sess.get(to_jina_url(row["sourceLink"]), timeout=25).text
                real_link = extract_buy_link_from_detail(detail_html)
                body_img = extract_body_image_from_detail(detail_html)
                row["buyLink"] = real_link or row["sourceLink"]
                row["desc"] = extract_body_text_from_detail(detail_html)
                if body_img:
                    row["img"] = body_img
                if 'quasarzone.com/' in row["buyLink"] and '/bbs/qb_saleinfo/views/' not in row["buyLink"]:
                    row["buyLink"] = row["sourceLink"]
            except Exception:
                row["buyLink"] = row["sourceLink"]

            row["date"] = date_label
            try:
                row["registeredAt"] = extract_registered_at_from_detail(detail_html, date_label)
            except Exception:
                row["registeredAt"] = f"{date_label}T00:00:00+09:00"

            try:
                registered_dt = datetime.fromisoformat(row["registeredAt"])
            except Exception:
                registered_dt = dt
            if registered_dt < since:
                old_count += 1
                continue

            row.pop("_detailViaJina", None)
            filtered.append(row)

        if old_count == len(rows):
            break

    today_label = str(now.date())
    yesterday_label = str((now - timedelta(days=1)).date())
    today_items = [item for item in filtered if item.get("date") == today_label]
    yesterday_items = [item for item in filtered if item.get("date") == yesterday_label]

    out = {
        "source": LIST_URL,
        "generatedAt": now.isoformat(),
        "rangeHours": 48,
        "since": since.isoformat(),
        "today": today_label,
        "yesterday": yesterday_label,
        "counts": {
            "today": len(today_items),
            "yesterday": len(yesterday_items),
            "total": len(filtered),
        },
        "items": filtered,
        "grouped": {"today": today_items, "yesterday": yesterday_items},
    }

    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {JSON_PATH} ({len(filtered)} items)")


if __name__ == "__main__":
    main()
