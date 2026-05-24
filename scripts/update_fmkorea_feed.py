#!/usr/bin/env python3
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests
from playwright.sync_api import sync_playwright

LIST_URL = "https://m.fmkorea.com/index.php?mid=hotdeal&sort_index=pop&order_type=desc&listStyle=webzine"
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "fmkorea_hotdeals_2days.json"
KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0"}


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


def extract_price_from_title(title: str) -> str:
    t = (title or "").strip()
    patterns = [
        r"([0-9][0-9,]*\s*원)",
        r"([0-9][0-9,]*\s*천원)",
        r"([0-9][0-9,]*\s*만원)",
        r"([0-9][0-9,]*\s*원대)",
        r"([0-9][0-9,]*\s*천원대)",
        r"([0-9][0-9,]*\s*만원대)",
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            return m.group(1).replace(" ", "")
    if "무료" in t:
        return "무료"
    if "다양" in t:
        return "다양"
    return ""


def normalize_fmkorea_outbound(link: str) -> str:
    raw = (link or '').strip()
    if not raw:
        return ''
    try:
        u = urlparse(raw)
        if 'link.fmkorea.org' in (u.netloc or '') and u.path.startswith('/link.php'):
            q = parse_qs(u.query)
            target = (q.get('url', [''])[0] or '').strip()
            if target:
                return unquote(target)
    except Exception:
        pass
    return raw


def canonical_fmkorea_source_link(link: str) -> str:
    raw = (link or '').strip()
    if not raw:
        return ''
    try:
        u = urlparse(raw)
        q = parse_qs(u.query)
        doc = (q.get('document_srl', [''])[0] or '').strip()
        if doc:
            return f'https://m.fmkorea.com/?mid=hotdeal&document_srl={doc}'
    except Exception:
        pass
    return raw


def run_page_extract(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1400)
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
        const img = imgEl ? ((imgEl.getAttribute('data-src') || imgEl.getAttribute('data-original') || imgEl.getAttribute('src') || '').trim()) : "";
        const lines = txt.split("\\n").map(s => s.trim()).filter(Boolean);
        rows.push({ title, href, img, lines, raw: txt });
      }
      return rows;
    }'''
    return page.evaluate(script)


def extract_primary_image(detail_html: str) -> str:
    body_m = re.search(r'<div[^>]+class="[^"]*xe_content[^"]*"[\s\S]*?</div>\s*</div>', detail_html, re.I)
    chunk = body_m.group(0) if body_m else detail_html

    for m in re.finditer(r'<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']', chunk, re.I):
        src = (m.group(1) or "").strip()
        if not src or src.startswith('data:') or '/logos/mobile/fmkorea.png' in src or 'transparent.gif' in src:
            continue
        if src.startswith("//"):
            return f"https:{src}"
        return src

    og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', detail_html, re.I)
    if og:
        src = (og.group(1) or "").strip()
        if src and '/logos/mobile/fmkorea.png' not in src:
            if src.startswith("//"):
                return f"https:{src}"
            return src
    return ""


def extract_detail_bundle_in_page(page, url: str) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(450)
    return page.evaluate('''() => {
      const result = { img: '', buyLink: '', desc: '' };

      const norm = (v) => (v || '').trim();
      const abs = (href) => {
        try { return new URL(href, location.href).href; } catch (_) { return ''; }
      };

      // 대표이미지 추출
      const imgScopes = ['.xe_content', '.rd_body', '.document-content', '.document-view', '.article-content', 'article'];
      let imgRoot = null;
      for (const sel of imgScopes) {
        imgRoot = document.querySelector(sel);
        if (imgRoot) break;
      }
      if (!imgRoot) imgRoot = document;
      for (const img of imgRoot.querySelectorAll('img')) {
        const src = (img.getAttribute('data-src') || img.getAttribute('src') || '').trim();
        if (!src) continue;
        if (src.startsWith('data:')) continue;
        if (src.includes('/logos/mobile/fmkorea.png')) continue;
        if (src.includes('transparent.gif')) continue;
        result.img = src.startsWith('//') ? `https:${src}` : src;
        break;
      }

      // 1) '링크' 라벨 옆 anchor 우선
      const cells = Array.from(document.querySelectorAll('th,td,dt,dd,li,span,div'));
      for (const el of cells) {
        const t = norm(el.textContent);
        if (t !== '링크' && !t.startsWith('링크')) continue;
        let next = el.nextElementSibling;
        if (next) {
          const a = next.querySelector('a[href^="http"]') || next.closest('tr,dl,li,div')?.querySelector('a[href^="http"]');
          if (a) {
            result.buyLink = abs(a.getAttribute('href'));
            break;
          }
          const txt = norm(next.textContent);
          const m = txt.match(/https?:\/\/\S+/);
          if (m) {
            result.buyLink = abs(m[0]);
            break;
          }
        }
        const wrap = el.closest('tr,dl,li,div');
        if (wrap) {
          const a2 = wrap.querySelector('a[href^="http"]');
          if (a2) {
            result.buyLink = abs(a2.getAttribute('href'));
            break;
          }
          const m2 = norm(wrap.textContent).match(/https?:\/\/\S+/);
          if (m2) {
            result.buyLink = abs(m2[0]);
            break;
          }
        }
      }

      // 2) 상단 정보영역에서 첫 외부링크 fallback
      if (!result.buyLink) {
        const topScopes = ['.rd_body', '.xe_content', '.document-content', 'article', 'body'];
        for (const sel of topScopes) {
          const root = document.querySelector(sel);
          if (!root) continue;
          for (const a of root.querySelectorAll('a[href^="http"]')) {
            const href = abs(a.getAttribute('href'));
            if (!href) continue;
            if (href.includes('fmkorea.com')) continue;
            result.buyLink = href;
            break;
          }
          if (result.buyLink) break;
        }
      }

      // 본문 텍스트
      const scopes = ['.xe_content', '.rd_body', '.document-content', '.document-view', '.article-content', 'article', 'body'];
      let root = null;
      for (const sel of scopes) {
        root = document.querySelector(sel);
        if (root) break;
      }
      if (root) result.desc = (root.innerText || '').trim();

      return result;
    }''')


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

        detail_page = context.new_page()
        for r in all_rows:
            try:
                bundle = extract_detail_bundle_in_page(detail_page, r["href"])

                current = (r.get("img") or "").strip()
                if (not current) or ("/logos/mobile/fmkorea.png" in current) or ("transparent.gif" in current):
                    picked = (bundle.get("img") or "").strip()
                    if picked:
                        r["img"] = picked

                buy = normalize_fmkorea_outbound(bundle.get("buyLink") or "")
                if buy:
                    r["buyLink"] = buy

                body_text = (bundle.get("desc") or "").strip()
                if body_text:
                    r["desc"] = body_text
            except Exception:
                pass
        detail_page.close()

        browser.close()

    s = requests.Session()
    s.headers.update(HEADERS)

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

        if price == "가격 정보 확인":
            fallback_price = extract_price_from_title(r["title"])
            if fallback_price:
                price = fallback_price

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
        doc_id = id_m.group(1)

        img = (r.get("img") or "").strip()
        if not img:
            try:
                detail_html = s.get(r["href"], timeout=20).text
                img = extract_primary_image(detail_html)
            except Exception:
                img = ""

        source_link = canonical_fmkorea_source_link(r["href"])

        items.append(
            {
                "id": doc_id,
                "title": title_clean or "제목 없음",
                "area": "펨딜",
                "dist": category,
                "time": time_token,
                "price": price,
                "likes": likes,
                "views": views,
                "comments": comments,
                "category": category,
                "desc": (r.get("desc") or f"쇼핑몰: {shop} / 배송: {delivery}".strip()),
                "img": img,
                "buyLink": normalize_fmkorea_outbound(r.get("buyLink") or r["href"]),
                "sourceLink": source_link,
                "source": "fmkorea",
                "date": dt.strftime("%Y-%m-%d"),
                "registeredAt": dt.isoformat(),
            }
        )

    dedup = {}
    for it in items:
        key = it.get("sourceLink") or it.get("id")
        if key and key not in dedup:
            dedup[key] = it
    items = list(dedup.values())

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
