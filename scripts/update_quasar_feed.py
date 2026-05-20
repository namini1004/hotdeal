#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

LIST_URL = "https://quasarzone.com/bbs/qb_saleinfo"
BASE = "https://quasarzone.com"
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "quasar_hotdeals_2days.json"
KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0"}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def parse_time_to_date_label(time_text: str, now: datetime) -> str:
    text = (time_text or "").strip()
    if "분 전" in text or "시간 전" in text or text in {"방금", "조금 전"}:
        return now.strftime("%Y-%m-%d")
    m = re.search(r"(\d{2})-(\d{2})", text)
    if m:
        mm, dd = int(m.group(1)), int(m.group(2))
        year = now.year
        # 연초 경계 처리
        if now.month == 1 and mm == 12:
            year -= 1
        return f"{year:04d}-{mm:02d}-{dd:02d}"
    return now.strftime("%Y-%m-%d")


def extract_buy_link_from_detail(detail_html: str) -> str:
    og_desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', detail_html)
    if og_desc_m:
        desc = html.unescape(og_desc_m.group(1))
        url_m = re.search(r'(https?://[^\s\]\)"\']+)', desc)
        if url_m:
            candidate = url_m.group(1).strip()
            if '…' not in candidate and '...' not in candidate:
                return candidate

    # 불명확한 배너/광고 링크 오검출 방지: 확실치 않으면 빈 값 반환
    return ''


def parse_list_items(page_html: str):
    rows = re.findall(r"<tr>[\s\S]*?<\/tr>", page_html)
    items = []
    seen = set()
    sess = requests.Session()
    sess.headers.update(HEADERS)

    for row in rows:
        link_m = re.search(r'href="(/bbs/qb_saleinfo/views/(\d+))"', row)
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
        price = clean(price_m.group(1)) if price_m else "가격 정보 확인"

        comments_m = re.search(r'class="ctn-count\s*">\s*([0-9,]+)\s*</span>', row)
        comments = int((comments_m.group(1).replace(',', '') if comments_m else '0') or '0')

        count_matches = re.findall(r'<span class="count">\s*([0-9.,kK]+)\s*</span>', row)
        views_text = count_matches[-1] if count_matches else '0'
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
                "likes": 0,
                "views": views,
                "comments": comments,
                "category": category,
                "desc": "",
                "img": img,
                "buyLink": "",
                "sourceLink": urljoin(BASE, rel_link),
                "source": "quasar",
            }
        )

    return items


def main():
    now = datetime.now(KST)
    since = now - timedelta(hours=48)
    html_text = requests.get(LIST_URL, headers=HEADERS, timeout=25).text
    rows = parse_list_items(html_text)

    filtered = []
    for row in rows:
        date_label = parse_time_to_date_label(row.get("time", ""), now)
        try:
            dt = datetime.fromisoformat(f"{date_label}T00:00:00+09:00")
        except Exception:
            dt = now
        if dt < since.replace(hour=0, minute=0, second=0, microsecond=0):
            continue

        # 사이트별 룰: 상세에서 실제 구매처 링크 추출
        try:
            detail_html = requests.get(row["sourceLink"], headers=HEADERS, timeout=25).text
            real_link = extract_buy_link_from_detail(detail_html)
            row["buyLink"] = real_link or row["sourceLink"]
            if 'quasarzone.com/' in row["buyLink"] and '/bbs/qb_saleinfo/views/' not in row["buyLink"]:
                row["buyLink"] = row["sourceLink"]
        except Exception:
            row["buyLink"] = row["sourceLink"]

        row["date"] = date_label
        row["registeredAt"] = f"{date_label}T00:00:00+09:00"
        filtered.append(row)

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
        "grouped": {"today": filtered, "yesterday": []},
    }

    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {JSON_PATH} ({len(filtered)} items)")


if __name__ == "__main__":
    main()
