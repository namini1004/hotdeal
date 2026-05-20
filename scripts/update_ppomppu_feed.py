#!/usr/bin/env python3
import base64
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests

LIST_URL = "https://m.ppomppu.co.kr/new/pop_bbs.php?id=ppomppu&bot_type=pop_bbs"
BASE = "https://m.ppomppu.co.kr"
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "ppomppu_hotdeals_2days.json"
HIDDEN_PATH = ROOT / "assets" / "hidden_hotdeals.json"
THUMB_DIR = ROOT / "assets" / "ppomppu_thumbs"
KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.ppomppu.co.kr/"}


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


def parse_post_stats(detail: str) -> tuple[int, int]:
    views = 0
    views_m = re.search(r'조회\s*:\s*([0-9,]+)', detail)
    if views_m:
        views = parse_int(views_m.group(1))

    comments = 0
    comments_m = re.search(r'<span class="list_comment">\s*([0-9,]+)\s*</span>', detail)
    if comments_m:
        comments = parse_int(comments_m.group(1))
    return views, comments


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


def parse_items():
    s = requests.Session()
    s.headers.update(HEADERS)

    # 페이지를 순회해서(더보기 포함) 링크를 충분히 수집
    link_rows = []
    seen_links = set()
    for page in range(1, 6):
        page_url = LIST_URL if page == 1 else f"{LIST_URL}&page={page}"
        list_html = s.get(page_url, timeout=20).text
        blocks = re.findall(r'<li class="none-border bbs_list_thumbnail new_sk "[\s\S]*?</li>', list_html)
        if not blocks:
            break

        new_in_page = 0
        for b in blocks:
            href_m = re.search(r'<a href="([^"]*bbs_view\.php[^"]+)"', b)
            title_m = re.search(r'<span class="cont"[^>]*>([\s\S]*?)</span>', b)
            img_m = re.search(r'<img src="([^"]+)"', b)
            cat_m = re.search(r'<li class="names">\[([^\]]+)\]', b)
            if not href_m or not title_m:
                continue

            href = urljoin(BASE, href_m.group(1))
            if href in seen_links:
                continue
            seen_links.add(href)
            new_in_page += 1

            raw_title = re.sub(r'<[^>]+>', '', title_m.group(1))
            raw_title = html.unescape(raw_title).strip()

            img = img_m.group(1) if img_m else ""
            if img.startswith('//'):
                img = 'https:' + img
            elif img.startswith('/'):
                img = urljoin(BASE, img)

            category = cat_m.group(1).strip() if cat_m else "기타"
            link_rows.append({"href": href, "raw_title": raw_title, "img": img, "category": category})

        if new_in_page == 0:
            break

    items = []
    for row in link_rows:
        href = row['href']
        raw_title = row['raw_title']
        img = row['img']
        category = row['category']

        detail = s.get(href, timeout=20).text
        og_title = pick(r'<meta property="og:title" content="([^"]*)"', detail) or raw_title
        og_desc = pick(r'<meta property="og:description" content="([^"]*)"', detail)
        og_img = pick(r'<meta property="og:image" content="([^"]*)"', detail) or img

        dt = parse_registered_at(detail)
        date_label = dt.strftime('%Y-%m-%d') if dt else ""
        registered_at = dt.isoformat() if dt else ""
        views, comments = parse_post_stats(detail)

        # 사러가기 URL (상단 닉네임 아래 링크의 실제 target)
        buy_link = ""
        s_m = re.search(r'href="(https://s\.ppomppu\.co\.kr\?[^\"]+)"', detail)
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
            "likes": 0,
            "views": views,
            "comments": comments,
            "category": category,
            "desc": og_desc or "",
            "img": og_img,
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
        for ext in ['.jpg', '.png', '.webp', '.gif']:
            p = THUMB_DIR / f'{nid}{ext}'
            if p.exists():
                local_rel = f'assets/ppomppu_thumbs/{nid}{ext}'
                break

        if not local_rel and src.startswith('http'):
            try:
                r = s.get(src, timeout=15)
                if r.status_code == 200 and len(r.content) > 500:
                    ext = ext_from_ct(r.headers.get('content-type', ''))
                    p = THUMB_DIR / f'{nid}{ext}'
                    p.write_bytes(r.content)
                    local_rel = f'assets/ppomppu_thumbs/{nid}{ext}'
            except Exception:
                pass

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
