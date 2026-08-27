#!/usr/bin/env python3
import html
import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None
try:
    from hotdeal_quality_signals import (
        QUALITY_SIGNAL_PARSER_VERSION,
        analyze_comment_quality,
        extract_comment_signal_text,
    )
except ModuleNotFoundError:
    from scripts.hotdeal_quality_signals import (
        QUALITY_SIGNAL_PARSER_VERSION,
        analyze_comment_quality,
        extract_comment_signal_text,
    )

LIST_URL = "https://m.fmkorea.com/index.php?mid=hotdeal&listStyle=webzine"
LIST_URL_CANDIDATES = [
    LIST_URL,
    "https://www.fmkorea.com/index.php?mid=hotdeal&listStyle=webzine",
]
MAX_PAGES = 10
INCREMENTAL_MAX_PAGES = int(os.environ.get("HOTDEAL_FMKOREA_INCREMENTAL_MAX_PAGES", "2"))
INCREMENTAL_TAIL_SAMPLE_SIZE = int(os.environ.get("HOTDEAL_FMKOREA_INCREMENTAL_TAIL_SAMPLE_SIZE", "3"))
BROWSER_FALLBACK_MAX_PAGES = int(os.environ.get("HOTDEAL_FMKOREA_BROWSER_FALLBACK_MAX_PAGES", "1"))
PAGE_DELAY_SECONDS = float(os.environ.get("HOTDEAL_FMKOREA_PAGE_DELAY_SECONDS", "8"))
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "assets" / "fmkorea_hotdeals_2days.json"
BACKOFF_STATE_PATH = Path(os.environ.get("HOTDEAL_FMKOREA_BACKOFF_STATE", str(ROOT / ".artifacts" / "fmkorea_backoff_state.json")))
BACKOFF_BASE_SECONDS = int(os.environ.get("HOTDEAL_FMKOREA_BACKOFF_BASE_SECONDS", "3600"))
BACKOFF_MAX_SECONDS = int(os.environ.get("HOTDEAL_FMKOREA_BACKOFF_MAX_SECONDS", "86400"))
BACKOFF_JITTER_RATIO = float(os.environ.get("HOTDEAL_FMKOREA_BACKOFF_JITTER_RATIO", "0.15"))
KST = timezone(timedelta(hours=9))
MAX_FUTURE_SKEW = timedelta(minutes=10)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}
FMKOREA_DIAGNOSTIC_DIR = os.environ.get("FMKOREA_DIAGNOSTIC_DIR", "").strip()
DEFAULT_BROWSER_PROFILE_DIR = ROOT / ".artifacts" / "fmkorea-browser-profile"
FMKOREA_DETAIL_PARSER_VERSION = 2


def env_bool(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def browser_fallback_enabled() -> bool:
    return env_bool("HOTDEAL_FMKOREA_BROWSER_FALLBACK", False)


def browser_fallback_headless() -> bool:
    return env_bool("HOTDEAL_FMKOREA_BROWSER_HEADLESS", False)


def browser_fallback_profile_dir() -> Path:
    raw = os.environ.get("HOTDEAL_FMKOREA_BROWSER_PROFILE_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_BROWSER_PROFILE_DIR


def ignore_backoff_enabled() -> bool:
    return env_bool("HOTDEAL_FMKOREA_IGNORE_BACKOFF", False)


def backoff_readonly_enabled() -> bool:
    return env_bool("HOTDEAL_FMKOREA_BACKOFF_READONLY", False)


def load_backoff_state() -> Dict:
    try:
        if BACKOFF_STATE_PATH.exists():
            data = json.loads(BACKOFF_STATE_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def save_backoff_state(state: Dict):
    BACKOFF_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BACKOFF_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_iso_datetime(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(KST)
    except Exception:
        return None


def backoff_delay_seconds(failures: int) -> int:
    base = min(BACKOFF_BASE_SECONDS * (2 ** max(0, failures - 1)), BACKOFF_MAX_SECONDS)
    jitter = random.uniform(0, max(0, base * BACKOFF_JITTER_RATIO))
    return int(min(base + jitter, BACKOFF_MAX_SECONDS))


def backoff_remaining_seconds(now: datetime):
    state = load_backoff_state()
    next_allowed = parse_iso_datetime(state.get("nextAllowedAt") or "")
    if not next_allowed or now >= next_allowed:
        return 0, state
    return int((next_allowed - now).total_seconds()), state


def record_security_backoff(now: datetime):
    state = load_backoff_state()
    failures = int(state.get("failures") or 0) + 1
    delay = backoff_delay_seconds(failures)
    next_allowed = now + timedelta(seconds=delay)
    state.update(
        {
            "failures": failures,
            "lastBlockedAt": now.isoformat(),
            "nextAllowedAt": next_allowed.isoformat(),
            "delaySeconds": delay,
        }
    )
    save_backoff_state(state)
    print(f"FMKOREA_BACKOFF_SET failures={failures} delaySeconds={delay} nextAllowedAt={next_allowed.isoformat()}")


def clear_backoff_state():
    state = load_backoff_state()
    if not state:
        return
    failures = int(state.get("failures") or 0)
    if failures > 0:
        print(f"FMKOREA_BACKOFF_RECOVERED previousFailures={failures}")
    save_backoff_state({"failures": 0, "lastSuccessAt": datetime.now(KST).isoformat()})


def parse_time_token(token: str, now: datetime):
    token = (token or "").strip()
    ymd = re.match(r"^(20\d{2})\.(\d{2})\.(\d{2})$", token)
    if ymd:
        try:
            candidate = datetime(int(ymd.group(1)), int(ymd.group(2)), int(ymd.group(3)), 0, 0, tzinfo=KST)
        except ValueError:
            return None
        return candidate if candidate <= now + MAX_FUTURE_SKEW else None
    hm = re.match(r"^(\d{2}):(\d{2})$", token)
    if hm:
        hour, minute = int(hm.group(1)), int(hm.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now + timedelta(minutes=5):
            candidate = candidate - timedelta(days=1)
        return candidate
    md = re.match(r"^(\d{2})\.(\d{2})$", token)
    if md:
        mm, dd = int(md.group(1)), int(md.group(2))
        if not (1 <= mm <= 12 and 1 <= dd <= 31):
            return None
        year = now.year
        try:
            candidate = datetime(year, mm, dd, 0, 0, tzinfo=KST)
        except ValueError:
            return None
        if candidate > now + MAX_FUTURE_SKEW:
            try:
                candidate = candidate.replace(year=year - 1)
            except ValueError:
                return None
        return candidate
    return None


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
        const timeToken = ((li.querySelector('.regdate') || {}).textContent || '').trim();
        const category = ((li.querySelector('.category') || {}).textContent || '').replace(/\\/\\s*$/, '').trim();
        rows.push({ title, href, img, lines, raw: txt, timeToken, category });
      }
      return rows;
    }'''
    return page.evaluate(script)


def strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def absolutize_fmkorea_url(href: str, base_url: str) -> str:
    href = html.unescape((href or "").strip())
    if href.startswith("//"):
        return f"https:{href}"
    return urljoin(base_url, href)


def extract_attr(fragment: str, attr_names) -> str:
    for name in attr_names:
        m = re.search(rf"{re.escape(name)}=[\"']([^\"']+)[\"']", fragment or "", re.I)
        if m:
            return html.unescape(m.group(1).strip())
    return ""


def parse_static_html_rows(page_html: str, base_url: str) -> List[Dict]:
    """Playwright가 보안 페이지에 막힐 때를 대비한 정적 HTML fallback 파서."""
    if "에펨코리아 보안 시스템" in (page_html or ""):
        return []

    chunks = re.findall(r"(<li\b[^>]*class=[\"'][^\"']*\bli\b[\s\S]*?</li>)", page_html or "", re.I)
    rows = []
    for chunk in chunks:
        if "document_srl=" not in chunk or "쇼핑몰:" not in chunk:
            continue

        href_m = re.search(r"<a[^>]+href=[\"']([^\"']*document_srl=[^\"']+)[\"']", chunk, re.I)
        if not href_m:
            continue
        href = absolutize_fmkorea_url(href_m.group(1), base_url)

        title_m = re.search(r"<span[^>]+class=[\"'][^\"']*ellipsis-target[^\"']*[\"'][^>]*>([\s\S]*?)</span>", chunk, re.I)
        if not title_m:
            title_m = re.search(r"<h3[^>]*[\s\S]*?<a[^>]+href=[\"'][^\"']*document_srl=[^\"']+[\"'][^>]*>([\s\S]*?)</a>[\s\S]*?</h3>", chunk, re.I)
        title = strip_tags(title_m.group(1) if title_m else "")
        if not title or "공지" in title:
            continue

        img_fragment_m = re.search(r"<img[^>]+>", chunk, re.I)
        img = ""
        if img_fragment_m:
            img_tag = img_fragment_m.group(0)
            img = extract_attr(img_tag, ["data-original", "data-src", "src"])
            img = absolutize_fmkorea_url(img, base_url) if img else ""

        raw = strip_tags(chunk)
        category_html_m = re.search(r"<span[^>]+class=[\"'][^\"']*category[^\"']*[\"'][^>]*>([\s\S]*?)</span>", chunk, re.I)
        category_from_html = strip_tags(category_html_m.group(1) if category_html_m else "").replace("/", "").strip()
        shop_m = re.search(r"쇼핑몰:\s*([^/]+?)\s*/\s*가격:", raw)
        price_m = re.search(r"가격:\s*([^/]+?)\s*/\s*배송:", raw)
        delivery_m = re.search(r"배송:\s*(.+?)(?:\s+[가-힣]+\s*/\s*(?:\d{2}:\d{2}|20\d{2}\.\d{2}\.\d{2}|\d{2}\.\d{2})|$)", raw)
        category_m = re.search(r"배송:.*?\s+([^/\s][^/]*?)\s*/\s*(\d{2}:\d{2}|20\d{2}\.\d{2}\.\d{2}|\d{2}\.\d{2})", raw)
        time_m = re.search(r"\b(\d{2}:\d{2}|20\d{2}\.\d{2}\.\d{2}|\d{2}\.\d{2})\b", raw)
        likes_m = re.search(r"추천\s*([0-9,]+)", raw)
        views_m = re.search(r"조회\s*([0-9.,만천백]+)", raw)

        shop = (shop_m.group(1).strip() if shop_m else "")
        price = (price_m.group(1).strip() if price_m else "")
        delivery = (delivery_m.group(1).strip() if delivery_m else "")
        category = category_from_html or (category_m.group(1).strip() if category_m else "기타")
        time_token = (category_m.group(2).strip() if category_m else (time_m.group(1).strip() if time_m else ""))
        likes = likes_m.group(1) if likes_m else "0"
        views = views_m.group(1) if views_m else "0"
        info_line = f"쇼핑몰: {shop} / 가격: {price} / 배송: {delivery}".strip()
        meta_line = f"{category} / {time_token} / 추천 {likes} / 조회 {views}".strip()
        rows.append({
            "title": title,
            "href": href,
            "img": img,
            "lines": [title, info_line, meta_line],
            "raw": raw,
            "timeToken": time_token,
            "category": category,
            "_listParser": "static",
        })
    return rows


def is_security_response(status_code: int, text: str) -> bool:
    return status_code == 430 or "에펨코리아 보안 시스템" in (text or "")


def fetch_static_page(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=25)
        text = res.text or ""
        rows = parse_static_html_rows(text, res.url or url)
        security = is_security_response(res.status_code, text)
        print(f"FMKOREA_STATIC_LIST url={url} status={res.status_code} rows={len(rows)} security={security}")
        return rows, security
    except Exception as exc:
        print(f"WARN_FMKOREA_STATIC_LIST_FAILED url={url} reason={exc}")
        return [], False


def fetch_static_page_rows(url: str) -> List[Dict]:
    rows, _security = fetch_static_page(url)
    return rows


def write_fmkorea_diagnostics(page, url: str, rows: List[Dict], label: str):
    """Actions에서 0건 파싱될 때 HTML/DOM 상태를 artifact로 남긴다."""
    if not FMKOREA_DIAGNOSTIC_DIR:
        return
    try:
        diag_dir = Path(FMKOREA_DIAGNOSTIC_DIR)
        diag_dir.mkdir(parents=True, exist_ok=True)
        safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "-", label).strip("-") or "page"
        payload = {
            "label": label,
            "url": url,
            "finalUrl": page.url,
            "title": page.title(),
            "rowCount": len(rows or []),
            "liCount": page.locator("li").count(),
            "documentLinks": page.locator("a[href*='document_srl=']").count(),
            "bodyTextSample": page.locator("body").inner_text(timeout=2000)[:3000],
        }
        (diag_dir / f"{safe_label}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (diag_dir / f"{safe_label}.html").write_text(page.content(), encoding="utf-8")
        print(f"WARN_FMKOREA_ZERO_ITEMS_DIAGNOSTIC path={diag_dir} label={label} url={url} rows={len(rows or [])}")
    except Exception as exc:
        print(f"WARN_FMKOREA_DIAGNOSTIC_FAILED label={label} reason={exc}")


def collect_recent_rows(page, now: datetime, since: datetime, previous_items: List[Dict] = None, page_factory=None):
    collected = []
    seen = set()
    last_rows = []
    last_url = ""
    previous_keys = previous_item_keys(previous_items or [])
    incremental = env_bool("HOTDEAL_FMKOREA_INCREMENTAL", True)
    max_pages = max(1, INCREMENTAL_MAX_PAGES if incremental else MAX_PAGES)
    security_blocked = False

    def get_browser_page():
        if page is not None:
            return page
        if page_factory is not None:
            return page_factory()
        return None

    for base_url in LIST_URL_CANDIDATES:
        source_rows = []
        source_seen = set()
        for pg in range(1, max_pages + 1):
            separator = "&" if "?" in base_url else "?"
            url = f"{base_url}{separator}page={pg}"
            rows, security = fetch_static_page(url)
            used_browser_fallback = False
            if security:
                browser_page = get_browser_page() if browser_fallback_enabled() else None
                if browser_page is not None:
                    print(f"FMKOREA_BROWSER_FALLBACK_TRY reason=static_security url={url}")
                    try:
                        rows = run_page_extract(browser_page, url)
                        used_browser_fallback = True
                    except Exception as exc:
                        print(f"WARN_FMKOREA_BROWSER_FALLBACK_FAILED url={url} reason={exc}")
                        rows = []
                    if rows:
                        security = False
                        print(f"FMKOREA_BROWSER_FALLBACK_RECOVERED url={url} rows={len(rows)}")
                    else:
                        security_blocked = True
                        break
                else:
                    security_blocked = True
                    break
            if not rows:
                browser_page = get_browser_page()
                if browser_page is not None:
                    rows = run_page_extract(browser_page, url)
                    used_browser_fallback = bool(rows)
            last_rows = rows
            last_url = url
            page_kept = 0
            for r in rows:
                if not should_keep_row_by_time(r, now, since):
                    continue
                page_kept += 1
                doc_id = extract_document_id_from_link(r.get("href") or "")
                key = doc_id or canonical_fmkorea_source_link(r.get("href") or "") or r.get("href")
                if key in source_seen:
                    continue
                source_seen.add(key)
                source_rows.append(r)
            if rows and page_kept == 0:
                break
            if used_browser_fallback and pg >= max(1, BROWSER_FALLBACK_MAX_PAGES):
                print(f"FMKOREA_BROWSER_FALLBACK_STOP reason=max_pages pages={max(1, BROWSER_FALLBACK_MAX_PAGES)}")
                break
            if incremental:
                if rows and page_tail_seen_in_previous(rows, previous_keys):
                    print(f"FMKOREA_INCREMENTAL_STOP reason=page_tail_seen page={pg} sample={max(1, INCREMENTAL_TAIL_SAMPLE_SIZE)}")
                    break
                if pg == 1:
                    if pg < max_pages:
                        print(f"FMKOREA_INCREMENTAL_CONTINUE reason=page1_tail_unseen delay={PAGE_DELAY_SECONDS:g}s")
                        time.sleep(PAGE_DELAY_SECONDS)
                elif pg >= max_pages:
                    print(f"FMKOREA_INCREMENTAL_STOP reason=max_pages pages={max_pages}")
        print(f"FMKOREA_LIST_CANDIDATE url={base_url} rows={len(source_rows)}")
        if source_rows:
            for r in source_rows:
                key = extract_document_id_from_link(r.get("href") or "") or canonical_fmkorea_source_link(r.get("href") or "") or r.get("href")
                if key in seen:
                    continue
                seen.add(key)
                collected.append(r)
            break
        if security_blocked:
            break

    if not collected and page is not None:
        write_fmkorea_diagnostics(page, last_url or LIST_URL, last_rows, "zero-list-rows")
    return collected, security_blocked


def is_low_quality_fmkorea_thumbnail(src: str) -> bool:
    return bool(re.search(r'/cache/thumb/', str(src or ''), re.I))


def _extract_balanced_element(source: str, start_match, tag: str) -> str:
    depth = 1
    token_pattern = re.compile(rf'<{tag}\b[^>]*>|</{tag}\s*>', re.I)
    for token in token_pattern.finditer(source, start_match.end()):
        if token.group(0).lower().startswith(f'</{tag}'):
            depth -= 1
            if depth == 0:
                return source[start_match.start():token.end()]
        elif not token.group(0).rstrip().endswith('/>'):
            depth += 1
    return source[start_match.start():]


def _fmkorea_body_text(chunk: str) -> str:
    value = re.sub(r'<!--[\s\S]*?-->', ' ', chunk or '')
    value = re.sub(r'<(?:script|style|noscript|iframe|object|svg|canvas)\b[^>]*>[\s\S]*?</(?:script|style|noscript|iframe|object|svg|canvas)\s*>', ' ', value, flags=re.I)
    value = re.sub(r'<br\s*/?>', '\n', value, flags=re.I)
    value = re.sub(r'</(?:p|div|section|article|h[1-6]|li|blockquote|tr|table)\s*>', '\n', value, flags=re.I)
    value = re.sub(r'<(?:p|div|section|article|h[1-6]|li|blockquote|tr|table)\b[^>]*>', '\n', value, flags=re.I)
    value = html.unescape(re.sub(r'<[^>]+>', ' ', value))

    lines = []
    for raw_line in value.replace('\r', '').split('\n'):
        line = re.sub(r'[ \t\f\v]+', ' ', raw_line).strip()
        if line:
            lines.append(line)
        elif lines and lines[-1] != '':
            lines.append('')
    while lines and lines[-1] == '':
        lines.pop()
    return '\n'.join(lines).strip()


def get_fmkorea_content_chunk(detail_html: str) -> str:
    source = detail_html or ''
    content_pattern = re.compile(
        r'<(?P<tag>div|section)\b[^>]*\bclass\s*=\s*["\'][^"\']*\bxe_content\b[^"\']*["\'][^>]*>',
        re.I,
    )

    article_m = re.search(r'<article\b[^>]*>', source, re.I)
    if article_m:
        article_chunk = _extract_balanced_element(source, article_m, 'article')
        body_m = content_pattern.search(article_chunk)
        if body_m:
            return _extract_balanced_element(article_chunk, body_m, body_m.group('tag').lower())

    candidates = []
    for body_m in content_pattern.finditer(source):
        chunk = _extract_balanced_element(source, body_m, body_m.group('tag').lower())
        opening_tag = body_m.group(0)
        score = len(_fmkorea_body_text(chunk))
        if re.search(r'\bdocument_\d+', opening_tag, re.I):
            score += 10000
        candidates.append((score, chunk))
    return max(candidates, key=lambda item: item[0])[1] if candidates else ''


def extract_fmkorea_body_text(detail_html: str) -> str:
    return _fmkorea_body_text(get_fmkorea_content_chunk(detail_html))


def extract_primary_image(detail_html: str) -> str:
    chunk = get_fmkorea_content_chunk(detail_html)
    low_quality_fallback = ""

    for m in re.finditer(r'''<img[^>]+(?:data-src|data-original|src)=["']([^"']+)["']''', chunk or '', re.I):
        src = (m.group(1) or "").strip()
        if not src or src.startswith('data:') or '/logos/mobile/fmkorea.png' in src or 'transparent.gif' in src or '/modules/point/icons/' in src:
            continue
        src = absolutize_fmkorea_url(src, 'https://www.fmkorea.com/')
        if is_low_quality_fmkorea_thumbnail(src):
            low_quality_fallback = low_quality_fallback or src
            continue
        return src

    og = re.search(r'''<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)''', detail_html, re.I)
    if og:
        src = (og.group(1) or "").strip()
        if src and '/logos/mobile/fmkorea.png' not in src:
            if src.startswith("//"):
                src = f"https:{src}"
            if not is_low_quality_fmkorea_thumbnail(src):
                return src
            low_quality_fallback = low_quality_fallback or src
    return low_quality_fallback


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
    bundle = page.evaluate(r'''() => {
      const result = { img: '', buyLink: '', desc: '', likes: 0, commentSignalText: '' };

      const norm = (v) => (v || '').trim();
      const abs = (href) => {
        try { return new URL(href, location.href).href; } catch (_) { return ''; }
      };
      const contentSelectors = [
        'article .xe_content[class*="document_"]',
        'article > .xe_content',
        '.rd_body article .xe_content',
        '.document-content',
        '.document-view',
        '.article-content',
        'article'
      ];
      let contentRoot = null;
      for (const sel of contentSelectors) {
        contentRoot = document.querySelector(sel);
        if (contentRoot) break;
      }
      if (!contentRoot) {
        let bestScore = -1;
        for (const candidate of document.querySelectorAll('.xe_content')) {
          const className = String(candidate.className || '');
          const textLength = norm(candidate.innerText).length;
          const score = textLength
            + (candidate.closest('article') ? 10000 : 0)
            + (/\bdocument_\d+/.test(className) ? 10000 : 0);
          if (score > bestScore) {
            bestScore = score;
            contentRoot = candidate;
          }
        }
      }

      // 대표이미지 추출
      const imgRoot = contentRoot || document;
      const isLowQualityFmkoreaThumb = (value) => /\/cache\/thumb\//i.test(value || '');
      let lowQualityFallback = '';
      for (const img of imgRoot.querySelectorAll('img')) {
        const src = (img.getAttribute('data-src') || img.getAttribute('data-original') || img.getAttribute('src') || '').trim();
        if (!src) continue;
        if (src.startsWith('data:')) continue;
        if (src.includes('/logos/mobile/fmkorea.png')) continue;
        if (src.includes('transparent.gif')) continue;
        if (src.includes('/modules/point/icons/')) continue;
        const resolved = src.startsWith('//') ? `https:${src}` : src;
        if (isLowQualityFmkoreaThumb(resolved)) {
          lowQualityFallback = lowQualityFallback || resolved;
          continue;
        }
        result.img = resolved;
        break;
      }
      if (!result.img && lowQualityFallback) result.img = lowQualityFallback;

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
      if (contentRoot) result.desc = (contentRoot.innerText || '').trim();

      const voted = document.querySelector('.btn_img.new_voted_count');
      const votedRaw = voted ? (voted.getAttribute('value') || voted.value || voted.textContent || '') : '';
      result.likes = Number(String(votedRaw).replace(/[^0-9]/g, '')) || 0;
      const commentRoots = Array.from(document.querySelectorAll('.fdb_lst_ul, .comment_list, #comment, .comment'));
      commentRoots.sort((a, b) => (b.innerText || '').length - (a.innerText || '').length);
      result.commentSignalText = commentRoots.length ? (commentRoots[0].innerText || '').trim() : '';

      return result;
    }''')

    try:
        rendered_html = page.content()
        parsed_desc = extract_fmkorea_body_text(rendered_html)
        if parsed_desc:
            bundle["desc"] = parsed_desc
            bundle["bodyParsed"] = True
        parsed_img = extract_primary_image(rendered_html)
        current_img = (bundle.get("img") or "").strip()
        if parsed_img and (not current_img or is_low_quality_fmkorea_thumbnail(current_img)):
            bundle["img"] = parsed_img
    except Exception:
        pass
    return bundle


def load_previous_items() -> List[Dict]:
    if not JSON_PATH.exists():
        return []
    try:
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        return list(data.get("items") or [])
    except Exception:
        return []


def previous_item_keys(items: List[Dict]) -> set:
    keys = set()
    for item in items or []:
        source_link = canonical_fmkorea_source_link(item.get("sourceLink") or "")
        doc_id = str(item.get("id") or "").strip() or extract_document_id_from_link(source_link)
        if doc_id:
            keys.add(f"id:{doc_id}")
        if source_link:
            keys.add(f"source:{source_link}")
    return keys


def extract_document_id_from_link(link: str) -> str:
    raw = link or ""
    m = re.search(r"[?&]document_srl=(\d+)", raw)
    return m.group(1) if m else ""


def row_identity_keys(row: Dict) -> set:
    href = row.get("href") or ""
    source_link = canonical_fmkorea_source_link(href)
    doc_id = extract_document_id_from_link(href)
    keys = set()
    if doc_id:
        keys.add(f"id:{doc_id}")
    if source_link:
        keys.add(f"source:{source_link}")
    return keys


def row_exists_in_previous(row: Dict, previous_keys: set) -> bool:
    return bool(row_identity_keys(row) & previous_keys)


def page_tail_seen_in_previous(rows: List[Dict], previous_keys: set) -> bool:
    if not rows or not previous_keys:
        return False
    sample_size = max(1, INCREMENTAL_TAIL_SAMPLE_SIZE)
    return any(row_exists_in_previous(row, previous_keys) for row in rows[-sample_size:])


def extract_row_meta(row: Dict, now: datetime) -> Dict:
    lines = [str(ln or "").strip() for ln in (row.get("lines") or []) if str(ln or "").strip()]
    title = str(row.get("title") or "").strip()
    time_pattern = r'(?:\d{2}:\d{2}|20\d{2}\.\d{2}\.\d{2}|\d{2}\.\d{2})'
    time_token = str(row.get("timeToken") or "").strip()
    if not re.fullmatch(time_pattern, time_token):
        time_token = ""
    category = str(row.get("category") or "").strip(" /\t") or "기타"
    time_line = ""
    stats_line = next((ln for ln in lines if "추천" in ln or "조회" in ln), "")

    if not time_token:
        for ln in lines:
            if ln == title:
                continue
            m_meta = re.search(rf'^(.*?)\s*/\s*({time_pattern})(?:\s*/|\s*$)', ln)
            if not m_meta:
                continue
            category = m_meta.group(1).strip(" /\t") or category
            time_token = m_meta.group(2).strip()
            time_line = ln
            break

    if not time_token:
        for ln in lines:
            if ln == title:
                continue
            if re.fullmatch(time_pattern, ln):
                time_token = ln
                time_line = ln
                break

    line_meta = " / ".join(dict.fromkeys(value for value in (time_line, stats_line) if value))

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
    if not dt or dt > now + MAX_FUTURE_SKEW:
        return False
    return not (dt < since and dt.date() != since.date())


def has_reusable_detail_fields(item: Dict) -> bool:
    buy_link = (item.get("buyLink") or "").strip()
    desc = (item.get("desc") or "").strip()
    if not buy_link or not desc:
        return False

    try:
        parser_version = int(item.get("detailParserVersion") or 0)
    except (TypeError, ValueError):
        parser_version = 0
    if parser_version >= FMKOREA_DETAIL_PARSER_VERSION:
        return True

    plain_desc = strip_tags(re.sub(r'<!--[\s\S]*?-->', ' ', desc))
    if re.fullmatch(r'쇼핑몰\s*:.*?/\s*배송\s*:.*', plain_desc, re.I):
        return False
    without_urls = re.sub(r'https?://[^\s<]+', ' ', plain_desc, flags=re.I)
    meaningful = re.sub(r'[\W_]+', '', without_urls, flags=re.UNICODE)
    return len(meaningful) >= 2


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
    try:
        parser_version = int(cached.get("detailParserVersion") or 0)
    except (TypeError, ValueError):
        parser_version = 0
    if parser_version:
        row["detailParserVersion"] = parser_version
    row["_detailCached"] = True
    row["commentSignalScore"] = 0
    row["positiveCommentSignals"] = 0
    row["negativeCommentSignals"] = 0
    row["qualitySignalParserVersion"] = QUALITY_SIGNAL_PARSER_VERSION
    return not is_low_quality_fmkorea_thumbnail(row.get("img") or "")


def write_feed_output(items: List[Dict], stale_fallback: bool, now: datetime, since: datetime):
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


def item_is_within_window(item: Dict, now: datetime, since: datetime) -> bool:
    raw = (item.get("registeredAt") or item.get("date") or "").strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return True
    local_dt = dt.astimezone(KST)
    if local_dt > now + MAX_FUTURE_SKEW:
        return False
    return not (local_dt < since and local_dt.date() != since.date())


def filter_items_within_window(items: List[Dict], now: datetime, since: datetime) -> List[Dict]:
    return [item for item in items or [] if item_is_within_window(item, now, since)]


def open_fmkorea_browser_context(playwright, use_browser_fallback=None):
    context_options = {
        "viewport": {"width": 390, "height": 844},
        "user_agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "locale": "ko-KR",
        "timezone_id": "Asia/Seoul",
    }
    if use_browser_fallback is None:
        use_browser_fallback = browser_fallback_enabled()
    if use_browser_fallback:
        profile_dir = browser_fallback_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)
        channel = os.environ.get("HOTDEAL_FMKOREA_BROWSER_CHANNEL", "chrome").strip() or "chrome"
        print(
            "FMKOREA_BROWSER_FALLBACK_ENABLED "
            f"profileDir={profile_dir} "
            f"channel={channel} "
            f"headless={browser_fallback_headless()}"
        )
        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                channel=channel,
                headless=browser_fallback_headless(),
                args=["--disable-blink-features=AutomationControlled"],
                **context_options,
            )
            return context, None
        except Exception as exc:
            print(f"WARN_FMKOREA_BROWSER_FALLBACK_CONTEXT_FAILED reason={exc}")

    launch_options = {"headless": True}
    channel = os.environ.get("HOTDEAL_FMKOREA_BROWSER_CHANNEL", "").strip()
    if channel:
        launch_options["channel"] = channel
    browser = playwright.chromium.launch(**launch_options)
    context = browser.new_context(**context_options)
    return context, browser


def main():
    now = datetime.now(KST)
    since = now - timedelta(hours=48)
    previous_items = filter_items_within_window(load_previous_items(), now, since)
    remaining, backoff_state = backoff_remaining_seconds(now)
    if remaining > 0 and not ignore_backoff_enabled():
        print(
            "FMKOREA_BACKOFF_SKIP "
            f"remainingSeconds={remaining} "
            f"nextAllowedAt={backoff_state.get('nextAllowedAt', '')} "
            f"failures={int(backoff_state.get('failures') or 0)}"
        )
        write_feed_output(previous_items, bool(previous_items), now, since)
        return

    previous_lookup = build_previous_detail_lookup(previous_items)
    s = requests.Session()
    s.headers.update(HEADERS)

    all_rows = []
    security_blocked = False

    if sync_playwright is None:
        print("WARN_FMKOREA_PLAYWRIGHT_UNAVAILABLE using_static_requests_only")
        all_rows, security_blocked = collect_recent_rows(None, now, since, previous_items)
        for r in all_rows:
            if apply_cached_detail_fields(r, previous_lookup):
                continue
            try:
                detail_html = s.get(r["href"], timeout=20).text
                picked = extract_primary_image(detail_html)
                if picked and not is_low_quality_fmkorea_thumbnail(picked):
                    r["img"] = picked
                    r["detailImg"] = picked
                body_text = extract_fmkorea_body_text(detail_html)
                if body_text:
                    r["desc"] = body_text
                    r["detailParserVersion"] = FMKOREA_DETAIL_PARSER_VERSION
                comment_quality = analyze_comment_quality(extract_comment_signal_text(detail_html))
                r["commentSignalScore"] = comment_quality["score"]
                r["positiveCommentSignals"] = comment_quality["positiveCount"]
                r["negativeCommentSignals"] = comment_quality["negativeCount"]
                r["qualitySignalParserVersion"] = QUALITY_SIGNAL_PARSER_VERSION
            except Exception:
                pass
    else:
        with sync_playwright() as p:
            context = None
            browser = None
            page = None

            def ensure_browser_page():
                nonlocal context, browser, page
                if page is None:
                    context, browser = open_fmkorea_browser_context(p, use_browser_fallback=browser_fallback_enabled())
                    page = context.new_page()
                return page

            if browser_fallback_enabled():
                all_rows, security_blocked = collect_recent_rows(None, now, since, previous_items, page_factory=ensure_browser_page)
            else:
                context, browser = open_fmkorea_browser_context(p, use_browser_fallback=False)
                page = context.new_page()
                all_rows, security_blocked = collect_recent_rows(page, now, since, previous_items)

            if context is None:
                context, browser = open_fmkorea_browser_context(p, use_browser_fallback=False)

            detail_page = context.new_page()
            for r in all_rows:
                if apply_cached_detail_fields(r, previous_lookup):
                    continue
                try:
                    bundle = extract_detail_bundle_in_page(detail_page, r["href"])

                    current = (r.get("img") or "").strip()
                    if (not current) or is_low_quality_fmkorea_thumbnail(current) or ("/logos/mobile/fmkorea.png" in current) or ("transparent.gif" in current):
                        picked = (bundle.get("img") or "").strip()
                        if (not picked) or is_low_quality_fmkorea_thumbnail(picked):
                            try:
                                detail_html = s.get(r["href"], timeout=20).text
                                picked = extract_primary_image(detail_html) or picked
                            except Exception:
                                pass
                        if picked and not is_low_quality_fmkorea_thumbnail(picked):
                            r["img"] = picked
                            r["detailImg"] = picked

                    buy = normalize_fmkorea_outbound(bundle.get("buyLink") or "")
                    if buy:
                        r["buyLink"] = buy

                    body_text = (bundle.get("desc") or "").strip()
                    if body_text:
                        r["desc"] = body_text
                    if bundle.get("bodyParsed"):
                        r["detailParserVersion"] = FMKOREA_DETAIL_PARSER_VERSION
                    bundle_likes = int(bundle.get("likes") or 0)
                    if bundle_likes:
                        r["detailLikes"] = bundle_likes
                    comment_quality = analyze_comment_quality(bundle.get("commentSignalText") or "")
                    r["commentSignalScore"] = comment_quality["score"]
                    r["positiveCommentSignals"] = comment_quality["positiveCount"]
                    r["negativeCommentSignals"] = comment_quality["negativeCount"]
                    r["qualitySignalParserVersion"] = QUALITY_SIGNAL_PARSER_VERSION
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

            context.close()
            if browser is not None:
                browser.close()

    items = []
    for r in all_rows:
        meta = r.get("_meta") or extract_row_meta(r, now)
        line_meta = meta["line_meta"]
        time_token = meta["time_token"]
        category = meta["category"]
        dt = meta["dt"]
        if not dt or dt > now + MAX_FUTURE_SKEW:
            continue
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
                "qualitySignalParserVersion": int(r.get("qualitySignalParserVersion") or QUALITY_SIGNAL_PARSER_VERSION),
                "category": category,
                "desc": (r.get("desc") or f"쇼핑몰: {shop} / 배송: {delivery}".strip()),
                "detailParserVersion": int(r.get("detailParserVersion") or 0),
                "img": img,
                "detailImg": (r.get("detailImg") or img),
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
    if sync_playwright is None:
        if previous_items and items and len(items) < int(len(previous_items) * 0.8):
            merged = {}
            for it in items + previous_items:
                key = it.get("sourceLink") or it.get("id")
                if key and key not in merged:
                    merged[key] = it
            print(f"WARN_FMKOREA_PARTIAL_STATIC_KEEP_PREVIOUS current={len(items)} previous={len(previous_items)} merged={len(merged)}")
            items = list(merged.values())
            stale_fallback = security_blocked
    if not items:
        if previous_items:
            items = previous_items
            stale_fallback = True
            print(f"WARN_FMKOREA_ZERO_ITEMS_KEEP_PREVIOUS previous={len(previous_items)} all_rows={len(all_rows)}")
        else:
            print(f"WARN_FMKOREA_ZERO_ITEMS_NO_PREVIOUS all_rows={len(all_rows)}")
    if security_blocked:
        stale_fallback = True

    write_feed_output(items, stale_fallback, now, since)
    if backoff_readonly_enabled():
        if security_blocked:
            print("FMKOREA_BACKOFF_READONLY_SECURITY")
        else:
            print("FMKOREA_BACKOFF_READONLY_SUCCESS")
    elif security_blocked:
        record_security_backoff(now)
    else:
        clear_backoff_state()


if __name__ == "__main__":
    main()
