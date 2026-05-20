#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

LIST_URL = "https://m.ruliweb.com/market/board/1020"
BASE = "https://bbs.ruliweb.com"
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "ruliweb_hotdeals_1day.json"
KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0"}


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


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


def parse_rows(page_html: str):
    rows = re.findall(r'<tr class="table_body[^\"]*">[\s\S]*?</tr>', page_html)
    items = []
    seen = set()

    for row in rows:
        if '>공지<' in row:
            continue

        title_m = re.search(r'subject_link deco" href="([^"]+)"[^>]*>\s*<strong>([\s\S]*?)</strong>', row, re.S)
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

        views_m = re.search(r'<td class="hit">\s*([0-9,]+)\s*</td>', row, re.S)
        views = int((views_m.group(1).replace(',', '') if views_m else '0') or '0')

        time_m = re.search(r'<td class="time">\s*([^<]+)\s*</td>', row, re.S)
        time_text = clean(time_m.group(1)) if time_m else ''

        price_m = re.search(r'\(([0-9,]+원)\)', title)
        price = price_m.group(1) if price_m else '가격 정보 확인'

        items.append(
            {
                "id": post_id,
                "title": title or "제목 없음",
                "area": "루딜",
                "dist": category,
                "time": time_text,
                "price": price,
                "likes": 0,
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


def get_content_chunk(detail_html: str) -> str:
    body_m = re.search(r'<div class="view_content[\s\S]*?</div>\s*</div>', detail_html)
    return body_m.group(0) if body_m else detail_html


def extract_buy_link(detail_html: str) -> str:
    # 본문 영역 우선 탐색
    chunk = get_content_chunk(detail_html)
    for m in re.finditer(r'href="(https?://[^\"]+)"', chunk):
        link = clean(m.group(1))
        if 'ruliweb.com' in link:
            continue
        return link
    return ''


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
    since = now - timedelta(hours=24)
    s = requests.Session()
    s.headers.update(HEADERS)

    page_html = s.get(LIST_URL, timeout=25).text
    rows = parse_rows(page_html)

    filtered = []
    for row in rows:
        dt = parse_time_to_datetime(row.get('time', ''), now)
        if dt < since:
            continue

        try:
            detail_html = s.get(row['sourceLink'], timeout=25).text
            img_m = re.search(r'<meta property="og:image" content="([^"]*)"', detail_html)
            desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', detail_html)
            primary_img = extract_primary_image(detail_html)
            row['img'] = to_proxy_image_url(primary_img or (clean(img_m.group(1)) if img_m else ''))
            row['desc'] = clean(desc_m.group(1)) if desc_m else ''
            row['buyLink'] = extract_buy_link(detail_html) or row['sourceLink']
        except Exception:
            row['buyLink'] = row['sourceLink']

        row['date'] = dt.strftime('%Y-%m-%d')
        row['registeredAt'] = dt.isoformat()
        filtered.append(row)

    out = {
        "source": LIST_URL,
        "generatedAt": now.isoformat(),
        "rangeHours": 24,
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
