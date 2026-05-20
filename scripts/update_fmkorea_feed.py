#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = "https://m.fmkorea.com"
LIST_URL = "https://m.fmkorea.com/index.php?mid=hotdeal&sort_index=pop&order_type=desc&listStyle=webzine"
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "fmkorea_hotdeals_1day.json"
KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0"}


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def parse_mmdd_to_datetime(mmdd: str, now: datetime) -> datetime:
    m = re.match(r"^(\d{2})\.(\d{2})$", (mmdd or "").strip())
    if not m:
        return now
    mm, dd = int(m.group(1)), int(m.group(2))
    year = now.year
    if now.month == 1 and mm == 12:
        year -= 1
    return datetime(year, mm, dd, 0, 0, tzinfo=KST)


def parse_views(v: str) -> int:
    text = (v or "").replace(",", "").strip().lower()
    try:
        if text.endswith("만"):
            return int(float(text[:-1]) * 10000)
        if text.endswith("천"):
            return int(float(text[:-1]) * 1000)
        return int(float(text))
    except Exception:
        return 0


def extract_buy_link(detail_html: str) -> str:
    content_m = re.search(r'<div class="xe_content[\s\S]*?</div>\s*</div>', detail_html)
    block = content_m.group(0) if content_m else detail_html
    for m in re.finditer(r'href="(https?://[^\"]+)"', block):
        link = html.unescape(m.group(1)).strip()
        if "fmkorea.com" in link or "static.fmkorea.com" in link:
            continue
        return link
    return ""


def parse_list_items(page_html: str):
    ol_m = re.search(r'<ol class=" bd_lst[\s\S]*?</ol>', page_html)
    chunk = ol_m.group(0) if ol_m else page_html
    rows = re.findall(r'<li class="[^\"]*?\bclear\b[^\"]*">[\s\S]*?</li>', chunk)
    out = []
    seen = set()

    for row in rows:
        if "공지" in row[:220]:
            continue

        link_m = re.search(r'href="([^"]*document_srl=(\d+)[^"]*)"', row)
        if not link_m:
            continue
        rel, post_id = html.unescape(link_m.group(1)), link_m.group(2)
        if post_id in seen:
            continue
        seen.add(post_id)

        title_m = re.search(r'<h3[^>]*>[\s\S]*?<a [^>]*>([\s\S]*?)</a>', row)
        title_raw = re.sub(r'<[^>]+>', '', title_m.group(1) if title_m else '')
        title = clean(title_raw)

        info = re.findall(r'<span><i class="fa fa-[^\"]+"></i>(?:<span>[^<]*</span>)?<b>(.*?)</b></span>', row)
        time_text = clean(info[0]) if len(info) >= 1 else ''
        category = clean(info[1]) if len(info) >= 2 else '기타'
        views_text = clean(info[2]) if len(info) >= 3 else '0'
        comments_text = clean(info[3]) if len(info) >= 4 else '0'

        price_m = re.search(r'\(([0-9,]+원)\)', title)
        price = price_m.group(1) if price_m else '가격 정보 확인'

        out.append(
            {
                "id": post_id,
                "title": title or "제목 없음",
                "area": "펨딜",
                "dist": category,
                "time": time_text,
                "price": price,
                "likes": 0,
                "views": parse_views(views_text),
                "comments": int(re.sub(r'[^0-9]', '', comments_text) or '0'),
                "category": category,
                "desc": "",
                "img": "",
                "buyLink": "",
                "sourceLink": urljoin(BASE, rel),
                "source": "fmkorea",
            }
        )

    return out


def main():
    now = datetime.now(KST)
    since = now - timedelta(hours=24)
    session = requests.Session()
    session.headers.update(HEADERS)

    rows = []
    for page in range(1, 4):
        url = f"{LIST_URL}&page={page}"
        html_text = session.get(url, timeout=25).text
        parsed = parse_list_items(html_text)
        if not parsed:
            break
        rows.extend(parsed)

    filtered = []
    seen = set()
    for row in rows:
        dt = parse_mmdd_to_datetime(row.get("time", ""), now)
        if dt < since:
            continue

        key = row.get("sourceLink", "")
        if key in seen:
            continue
        seen.add(key)

        try:
            detail_html = session.get(row["sourceLink"], timeout=25).text
            og_img = re.search(r'<meta property="og:image" content="([^"]*)"', detail_html)
            og_desc = re.search(r'<meta property="og:description" content="([^"]*)"', detail_html)
            row["img"] = clean(og_img.group(1)) if og_img else row.get("img", "")
            row["desc"] = clean(og_desc.group(1)) if og_desc else row.get("desc", "")
            row["buyLink"] = extract_buy_link(detail_html) or row["sourceLink"]
        except Exception:
            row["buyLink"] = row["sourceLink"]

        row["date"] = dt.strftime("%Y-%m-%d")
        row["registeredAt"] = dt.isoformat()
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

    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {JSON_PATH} ({len(filtered)} items)")


if __name__ == "__main__":
    main()
