#!/usr/bin/env python3
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

LIST_URL = "https://m.fmkorea.com/index.php?mid=hotdeal&sort_index=pop&order_type=desc&listStyle=webzine"
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "fmkorea_hotdeals_2days.json"
KST = timezone(timedelta(hours=9))


def parse_time_token(token: str, now: datetime):
    token = (token or "").strip()
    hm = re.match(r"^(\d{2}):(\d{2})$", token)
    if hm:
        return now.replace(hour=int(hm.group(1)), minute=int(hm.group(2)), second=0, microsecond=0)
    md = re.match(r"^(\d{2})\.(\d{2})$", token)
    if md:
        mm, dd = int(md.group(1)), int(md.group(2))
        if not (1 <= mm <= 12 and 1 <= dd <= 31):
            return now
        year = now.year
        if now.month == 1 and mm == 12:
            year -= 1
        return datetime(year, mm, dd, 0, 0, tzinfo=KST)
    return now


def run_page_extract(page, url):
    page.goto(url, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(2000)
    script = '''() => {
      const rows = [];
      for (const li of document.querySelectorAll("li")) {
        const txt = (li.innerText || "").trim();
        const hasDealLike = txt.includes("쇼핑몰:") || txt.includes("조회") || txt.includes("추천");
        if (!hasDealLike) continue;

        const titleEl = li.querySelector("h3 a") || li.querySelector("h3") || li.querySelector("a[href*='document_srl=']");
        const title = ((titleEl && titleEl.innerText) || "").trim();
        if (!title) continue;
        if (title.includes("공지")) continue;

        const hrefEl = li.querySelector("a[href*='document_srl=']") || li.querySelector("a[href]");
        const href = hrefEl ? hrefEl.href : "";
        if (!href || !href.includes("document_srl=")) continue;

        const imgEl = li.querySelector("img");
        const img = imgEl ? imgEl.src : "";
        const lines = txt.split("\\n").map(s => s.trim()).filter(Boolean);
        rows.push({ title, href, img, lines, raw: txt });
      }
      return rows;
    }'''
    return page.evaluate(script)


def main():
    now = datetime.now(KST)
    since = now - timedelta(hours=48)

    all_rows = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page = context.new_page()

        for pg in range(1, 4):
            url = f"{LIST_URL}&page={pg}"
            rows = run_page_extract(page, url)
            for r in rows:
                if r["href"] in seen:
                    continue
                seen.add(r["href"])
                all_rows.append(r)

        browser.close()

    items = []
    for r in all_rows:
        line_meta = ""
        for ln in r["lines"]:
            if " / " in ln and ("추천" in ln or "조회" in ln):
                line_meta = ln
                break

        # 예: 먹거리 / 12:01 / 작성자 / 추천 24
        time_token = ""
        category = "기타"
        m_meta = re.search(r'^(.*?)\s*/\s*(\d{2}:\d{2}|\d{2}\.\d{2})\s*/', line_meta)
        if m_meta:
            category = m_meta.group(1).strip() or "기타"
            time_token = m_meta.group(2).strip()
        else:
            tm = re.search(r'(\d{2}:\d{2}|\d{2}\.\d{2})', line_meta or r["raw"])
            if tm:
                time_token = tm.group(1)

        dt = parse_time_token(time_token, now)
        if dt < since:
            continue

        shop = ""
        price = "가격 정보 확인"
        delivery = ""
        for ln in r["lines"]:
            if ln.startswith("쇼핑몰:"):
                m = re.search(r"쇼핑몰:\s*([^/]+)\s*/\s*가격:\s*([^/]+)\s*/\s*배송:\s*(.+)$", ln)
                if m:
                    shop = m.group(1).strip()
                    price = m.group(2).strip()
                    delivery = m.group(3).strip()
                break

        comments_m = re.search(r"\[([0-9,]+)\]\s*$", r["title"])
        comments = int((comments_m.group(1).replace(",", "") if comments_m else "0") or "0")
        likes_m = re.search(r"추천\s*([0-9,]+)", line_meta)
        likes = int((likes_m.group(1).replace(",", "") if likes_m else "0") or "0")
        views_m = re.search(r"조회\s*([0-9.,만천백]+)", r["raw"])
        views = 0
        if views_m:
            v = views_m.group(1).replace(",", "")
            try:
                if v.endswith("백만"):
                    views = int(float(v[:-2]) * 1_000_000)
                elif v.endswith("만"):
                    views = int(float(v[:-1]) * 10000)
                elif v.endswith("천"):
                    views = int(float(v[:-1]) * 1000)
                else:
                    views = int(float(v))
            except Exception:
                views = 0

        title_clean = re.sub(r"\s*\[[0-9,]+\]\s*$", "", r["title"]).strip()

        id_m = re.search(r"document_srl=(\d+)", r["href"])
        if not id_m:
            continue

        items.append(
            {
                "id": id_m.group(1),
                "title": title_clean or "제목 없음",
                "area": "펨딜",
                "dist": category,
                "time": time_token,
                "price": price,
                "likes": likes,
                "views": views,
                "comments": comments,
                "category": category,
                "desc": f"쇼핑몰: {shop} / 배송: {delivery}".strip(),
                "img": r["img"],
                "buyLink": r["href"],
                "sourceLink": r["href"],
                "source": "fmkorea",
                "date": dt.strftime("%Y-%m-%d"),
                "registeredAt": dt.isoformat(),
            }
        )

    out = {
        "source": LIST_URL,
        "generatedAt": now.isoformat(),
        "rangeHours": 48,
        "since": since.isoformat(),
        "today": str(now.date()),
        "yesterday": str((now - timedelta(days=1)).date()),
        "counts": {"today": len(items), "yesterday": 0, "total": len(items)},
        "items": items,
        "grouped": {"today": items, "yesterday": []},
    }

    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {JSON_PATH} ({len(items)} items)")


if __name__ == "__main__":
    main()
