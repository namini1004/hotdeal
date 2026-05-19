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
THUMB_DIR = ROOT / "assets" / "ppomppu_thumbs"
KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.ppomppu.co.kr/"}


def pick(pattern: str, text: str) -> str:
    m = re.search(pattern, text)
    return html.unescape(m.group(1)).strip() if m else ""


def parse_items():
    s = requests.Session()
    s.headers.update(HEADERS)
    list_html = s.get(LIST_URL, timeout=20).text
    blocks = re.findall(r'<li class="none-border bbs_list_thumbnail new_sk "[\s\S]*?</li>', list_html)

    items = []
    seen = set()
    for b in blocks:
        href_m = re.search(r'<a href="([^"]*bbs_view\.php[^"]+)"', b)
        title_m = re.search(r'<span class="cont"[^>]*>([\s\S]*?)</span>', b)
        img_m = re.search(r'<img src="([^"]+)"', b)
        cat_m = re.search(r'<li class="names">\[([^\]]+)\]', b)
        if not href_m or not title_m:
            continue

        href = urljoin(BASE, href_m.group(1))
        if href in seen:
            continue
        seen.add(href)

        raw_title = re.sub(r'<[^>]+>', '', title_m.group(1))
        raw_title = html.unescape(raw_title).strip()

        img = img_m.group(1) if img_m else ""
        if img.startswith('//'):
            img = 'https:' + img
        elif img.startswith('/'):
            img = urljoin(BASE, img)

        category = cat_m.group(1).strip() if cat_m else "기타"

        detail = s.get(href, timeout=20).text
        og_title = pick(r'<meta property="og:title" content="([^"]*)"', detail) or raw_title
        og_desc = pick(r'<meta property="og:description" content="([^"]*)"', detail)
        og_img = pick(r'<meta property="og:image" content="([^"]*)"', detail) or img

        ts_m = re.search(r'G_BBS_REG_DATE\s*=\s*"(\d+)"', detail)
        dt = None
        if ts_m:
            ts = int(ts_m.group(1))
            if ts > 1000000000:
                dt = datetime.fromtimestamp(ts, tz=KST)
        date_label = dt.strftime('%Y-%m-%d') if dt else ""

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
        price = pm.group(1) if pm else "가격 정보 확인"

        items.append({
            "id": str(len(items) + 1),
            "title": og_title,
            "area": "뽐뿌 핫딜",
            "dist": category,
            "time": date_label,
            "price": price,
            "likes": 0,
            "category": category,
            "desc": og_desc or "",
            "img": og_img,
            "buyLink": buy_link,
            "sourceLink": href,
            "date": date_label,
        })

    today = datetime.now(KST).date()
    yesterday = today - timedelta(days=1)

    filtered = [it for it in items if it.get('date') in {str(today), str(yesterday)}]
    for i, it in enumerate(filtered, 1):
        it['id'] = str(i)

    grouped = {"today": [], "yesterday": []}
    for it in filtered:
        if it['date'] == str(today):
            grouped['today'].append(it)
        elif it['date'] == str(yesterday):
            grouped['yesterday'].append(it)

    out = {
        "source": LIST_URL,
        "generatedAt": datetime.now(KST).isoformat(),
        "today": str(today),
        "yesterday": str(yesterday),
        "counts": {
            "today": len(grouped["today"]),
            "yesterday": len(grouped["yesterday"]),
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
