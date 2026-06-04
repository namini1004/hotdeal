#!/usr/bin/env python3
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, unquote, urlparse

import requests
from playwright.sync_api import sync_playwright
try:
    from hotdeal_quality_signals import analyze_comment_quality
except ModuleNotFoundError:
    from scripts.hotdeal_quality_signals import analyze_comment_quality

LIST_URL = "https://m.fmkorea.com/index.php?mid=hotdeal&listStyle=webzine"
MAX_PAGES = 10
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "fmkorea_hotdeals_2days.json"
KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0"}


def parse_time_token(token: str, now: datetime):
    token = (token or "").strip()
    ymd = re.match(r"^(20\d{2})\.(\d{2})\.(\d{2})$", token)
    if ymd:
        return datetime(int(ymd.group(1)), int(ymd.group(2)), int(ymd.group(3)), 0, 0, tzinfo=KST)
    hm = re.match(r"^(\d{2}):(\d{2})$", token)
    if hm:
        candidate = now.replace(hour=int(hm.group(1)), minute=int(hm.group(2)), second=0, microsecond=0)
        if candidate > now + timedelta(minutes=5):
            candidate = candidate - timedelta(days=1)
        return candidate
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


def parse_detail_voted_count(detail_html: str) -> int:
    patterns = [
        r'class=["\'][^"\']*btn_img[^"\']*new_voted_count[^"\']*["\'][^>]*\bvalue=["\']?([0-9,]+)',
        r'class=["\'][^"\']*new_voted_count[^"\']*btn_img[^"\']*["\'][^>]*\bvalue=["\']?([0-9,]+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, detail_html, re.I)
        if m:
            return int((m.group(1) or '0').replace(',', '') or '0')
    return 0


def extract_detail_bundle_in_page(page, url: str) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(450)
    return page.evaluate('''() => {
      const result = { img: '', buyLink: '', desc: '', likes: 0, commentSignalText: '' };

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

      const voted = document.querySelector('.btn_img.new_voted_count');
      const votedRaw = voted ? (voted.getAttribute('value') || voted.value || voted.textContent || '') : '';
      result.likes = Number(String(votedRaw).replace(/[^0-9]/g, '')) || 0;
      const commentRoot = document.querySelector('.comment, .comment_list, .fdb_lst_ul, .xe_content') || document;
      result.commentSignalText = (commentRoot.innerText || '').trim();

      return result;
    }''')


def load_previous_items() -> List[Dict]:
    if not JSON_PATH.exists():
        return []
    try:
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        return list(data.get("items") or [])
    except Exception:
        return []


def extract_document_id_from_link(link: str) -> str:
    raw = link or ""
    m = re.search(r"[?&]document_srl=(\d+)", raw)
    return m.group(1) if m else ""


def extract_row_meta(row: Dict, now: datetime) -> Dict:
    line_meta = ""
    for ln in row.get("lines") or []:
        if " / " in ln and ("추천" in ln or "조회" in ln):
            line_meta = ln
            break

    time_token = ""
    category = "기타"
    time_pattern = r'(?:\d{2}:\d{2}|20\d{2}\.\d{2}\.\d{2}|\d{2}\.\d{2})'
    m_meta = re.search(rf'^(.*?)\s*/\s*({time_pattern})\s*/', line_meta)
    if m_meta:
        category = m_meta.group(1).strip() or "기타"
        time_token = m_meta.group(2).strip()
    else:
        tm = re.search(time_pattern, line_meta or row.get("raw") or "")
        if tm:
            time_token = tm.group(0)

    return {
        "line_meta": line_meta,
        "time_token": time_token,
        "category": category,
        "dt": parse_time_token(time_token, now),
    }


def should_keep_row_by_time(row: Dict, now: datetime, since: datetime) -> bool:
    meta = extract_row_meta(row, now)
    row["_meta"] = meta
    dt = meta["dt"]
    return not (dt < since and dt.date() != since.date())


def has_reusable_detail_fields(item: Dict) -> bool:
    return bool((item.get("buyLink") or "").strip() and (item.get("desc") or "").strip())


def build_previous_detail_lookup(items: List[Dict]) -> Dict[str, Dict]:
    lookup: Dict[str, Dict] = {}
    for item in items or []:
        if not has_reusable_detail_fields(item):
            continue
        item_id = str(item.get("id") or "").strip()
        source_link = str(item.get("sourceLink") or "").strip()
        doc_id = item_id or extract_document_id_from_link(source_link)
        if doc_id:
            lookup[f"id:{doc_id}"] = item
        if source_link:
            lookup[f"source:{canonical_fmkorea_source_link(source_link)}"] = item
    return lookup


def apply_cached_detail_fields(row: Dict, lookup: Dict[str, Dict]) -> bool:
    doc_id = extract_document_id_from_link(row.get("href") or "")
    source_link = canonical_fmkorea_source_link(row.get("href") or "")
    cached = lookup.get(f"id:{doc_id}") if doc_id else None
    if not cached and source_link:
        cached = lookup.get(f"source:{source_link}")
    if not cached or not has_reusable_detail_fields(cached):
        return False

    for key in ("img", "buyLink", "desc"):
        value = (cached.get(key) or "").strip()
        if value:
            row[key] = value
    row["_detailCached"] = True
    return True


def main():
    now = datetime.now(KST)
    since = now - timedelta(hours=48)
    previous_lookup = build_previous_detail_lookup(load_previous_items())

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

        for pg in range(1, MAX_PAGES + 1):
            url = f"{LIST_URL}&page={pg}"
            rows = run_page_extract(page, url)
            page_kept = 0
            for r in rows:
                if not should_keep_row_by_time(r, now, since):
                    continue
                page_kept += 1
                doc_id = extract_document_id_from_link(r.get("href") or "")
                key = doc_id or canonical_fmkorea_source_link(r.get("href") or "") or r.get("href")
                if key in seen:
                    continue
                seen.add(key)
                all_rows.append(r)
            if rows and page_kept == 0:
                break

        detail_page = context.new_page()
        for r in all_rows:
            if apply_cached_detail_fields(r, previous_lookup):
                continue
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
                bundle_likes = int(bundle.get("likes") or 0)
                if bundle_likes:
                    r["detailLikes"] = bundle_likes
                comment_quality = analyze_comment_quality(bundle.get("commentSignalText") or body_text)
                r["commentSignalScore"] = comment_quality["score"]
                r["positiveCommentSignals"] = comment_quality["positiveCount"]
                r["negativeCommentSignals"] = comment_quality["negativeCount"]
                doc_id = extract_document_id_from_link(r.get("href") or "")
                source_link = canonical_fmkorea_source_link(r.get("href") or "")
                if has_reusable_detail_fields(r):
                    if doc_id:
                        previous_lookup[f"id:{doc_id}"] = r
                    if source_link:
                        previous_lookup[f"source:{source_link}"] = r
            except Exception:
                pass
        detail_page.close()

        browser.close()

    s = requests.Session()
    s.headers.update(HEADERS)

    items = []
    for r in all_rows:
        meta = r.get("_meta") or extract_row_meta(r, now)
        line_meta = meta["line_meta"]
        time_token = meta["time_token"]
        category = meta["category"]
        dt = meta["dt"]
        if dt < since and dt.date() != since.date():
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
        likes = int(r.get("detailLikes") or likes or 0)
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
        if not img and not r.get("_detailCached"):
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
                "commentSignalScore": int(r.get("commentSignalScore") or 0),
                "positiveCommentSignals": int(r.get("positiveCommentSignals") or 0),
                "negativeCommentSignals": int(r.get("negativeCommentSignals") or 0),
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

    stale_fallback = False
    if not items:
        previous_items = load_previous_items()
        if previous_items:
            items = previous_items
            stale_fallback = True
            print(f"WARN_FMKOREA_ZERO_ITEMS_KEEP_PREVIOUS previous={len(previous_items)} all_rows={len(all_rows)}")
        else:
            print(f"WARN_FMKOREA_ZERO_ITEMS_NO_PREVIOUS all_rows={len(all_rows)}")

    out = {
        "source": LIST_URL,
        "sourceKey": "fmkorea",
        "staleFallback": stale_fallback,
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
