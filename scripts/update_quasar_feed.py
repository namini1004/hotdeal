#!/usr/bin/env python3
import html
import json
import os
import random
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup, SoupStrainer
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

LIST_URL = "https://quasarzone.com/bbs/qb_saleinfo"
BASE = "https://quasarzone.com"
MAX_PAGES = max(1, int(os.environ.get("HOTDEAL_QUASAR_MAX_PAGES", "8")))
INCREMENTAL_TAIL_SAMPLE_SIZE = int(os.environ.get("HOTDEAL_QUASAR_INCREMENTAL_TAIL_SAMPLE_SIZE", "3"))
PARTIAL_SNAPSHOT = os.environ.get("HOTDEAL_QUASAR_PARTIAL_SNAPSHOT", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
FETCH_MODE = os.environ.get("HOTDEAL_QUASAR_FETCH_MODE", "requests").strip().lower()
NEW_DETAIL_DELAY_SECONDS = max(0.0, float(os.environ.get("HOTDEAL_QUASAR_NEW_DETAIL_DELAY_SECONDS", "0")))
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = Path(
    os.environ.get("HOTDEAL_QUASAR_JSON_PATH", str(ROOT / "assets" / "quasar_hotdeals_2days.json"))
).expanduser()
KST = timezone(timedelta(hours=9))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Referer": "https://quasarzone.com/bbs/qb_saleinfo",
}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def parse_time_to_datetime(time_text: str, now: datetime) -> datetime:
    text = clean(time_text)
    if text in {"방금", "방금 전", "조금 전"}:
        return now

    relative = re.fullmatch(r"(\d+)\s*(초|분|시간|일)\s*전", text)
    if relative:
        seconds = {"초": 1, "분": 60, "시간": 3600, "일": 86400}
        return now - timedelta(seconds=int(relative.group(1)) * seconds[relative.group(2)])

    dated = re.fullmatch(r"(\d{4}|\d{2})[.-](\d{2})[.-](\d{2})", text)
    if dated:
        year, month, day = map(int, dated.groups())
        return datetime(year + 2000 if year < 100 else year, month, day, tzinfo=KST)

    m = re.fullmatch(r"(\d{2})[.-](\d{2})", text)
    if m:
        mm, dd = int(m.group(1)), int(m.group(2))
        year = now.year
        # 연초 경계 처리
        if now.month == 1 and mm == 12:
            year -= 1
        return datetime(year, mm, dd, 0, 0, tzinfo=KST)

    raise ValueError(f"Unknown Quasar list timestamp: {text!r}")


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
        '/homepage/real/themes/',
        'util_bt_',
        'emoticon',
        'avatar',
        'profile',
        'blank.',
        'transparent.',
    ]
    return not any(token in src_l for token in blocked)


def parse_int(value: str):
    m = re.search(r'(\d{1,5})', str(value or ''))
    return int(m.group(1)) if m else None


def image_size_from_tag(tag: str):
    width = height = None
    for attr in ('width', 'data-width'):
        m = re.search(rf'\b{attr}=[\"\']?([^\"\'\s>]+)', tag, re.I)
        if m:
            width = parse_int(m.group(1))
            break
    for attr in ('height', 'data-height'):
        m = re.search(rf'\b{attr}=[\"\']?([^\"\'\s>]+)', tag, re.I)
        if m:
            height = parse_int(m.group(1))
            break

    style_m = re.search(r'\bstyle=[\"\']([^\"\']+)', tag, re.I)
    if style_m:
        style = style_m.group(1)
        width_m = re.search(r'\bwidth\s*:\s*([^;]+)', style, re.I)
        height_m = re.search(r'\bheight\s*:\s*([^;]+)', style, re.I)
        if width_m and not width:
            width = parse_int(width_m.group(1))
        if height_m and not height:
            height = parse_int(height_m.group(1))
    return width, height


def image_size_from_url(src: str):
    text = html.unescape(src or '')
    patterns = [
        r'(?<!\d)(\d{2,4})[xX](\d{2,4})(?!\d)',
        r'(?<!\d)(\d{2,4})_(\d{2,4})(?!\d)',
        r'[?&](?:w|width)=(\d{2,4}).*?[?&](?:h|height)=(\d{2,4})',
        r'[?&](?:h|height)=(\d{2,4}).*?[?&](?:w|width)=(\d{2,4})',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None, None


def is_too_small_image(tag: str, src: str) -> bool:
    width, height = image_size_from_tag(tag)
    url_width, url_height = image_size_from_url(src)
    width = width or url_width
    height = height or url_height
    if width and width <= 100:
        return True
    if height and height <= 100:
        return True
    return False


def get_img_src_from_tag(tag: str) -> str:
    """lazy 이미지에서 placeholder src보다 실제 data-* 원본을 우선한다."""
    for attr in ("data-src", "data-original", "data-url", "src"):
        m = re.search(rf'\b{attr}=[\"\']([^\"\']+)', tag, re.I)
        if m:
            candidate = normalize_image_url(m.group(1))
            if is_body_image_candidate(candidate) and not is_too_small_image(tag, candidate):
                return candidate

    srcset_m = re.search(r'\bsrcset=[\"\']([^\"\']+)', tag, re.I)
    if srcset_m:
        for part in srcset_m.group(1).split(','):
            candidate = normalize_image_url(part.strip().split()[0] if part.strip() else '')
            if is_body_image_candidate(candidate) and not is_too_small_image(tag, candidate):
                return candidate

    return ''


def trim_to_after_price_area(body_html: str) -> str:
    """상단 프로필/작성자 영역을 피하고 가격/배송 정보 뒤 본문 이미지부터 보게 한다."""
    markers = [
        r'>\s*가격\s*<',
        r'>\s*배송(?:비|비/직배)?\s*<',
        r'\|\s*가격\s+',
        r'\|\s*배송(?:비|비/직배)?\s+',
    ]
    last_end = -1
    for pattern in markers:
        for m in re.finditer(pattern, body_html, re.I):
            last_end = max(last_end, m.end())
    if last_end < 0:
        return body_html
    close_m = re.search(r'(?:</tr>|</table>|</dl>|</ul>|</section>|</div>)', body_html[last_end:], re.I)
    if close_m:
        return body_html[last_end + close_m.end():]
    return body_html[last_end:]


def iter_detail_body_html(detail_html: str):
    """퀘이사 상세에서 가격/배송 표 이후의 실제 본문 영역 후보만 순서대로 반환한다."""
    # 1) 원본 HTML: 가격/배송 메타 뒤 실제 본문은 textarea#org_contents 안에 보관된다.
    for body_m in re.finditer(r'<textarea[^>]*\bid=[\"\']org_contents[\"\'][^>]*>([\s\S]*?)</textarea>', detail_html, re.I):
        yield trim_to_after_price_area(html.unescape(body_m.group(1)))

    # 2) 일부 렌더/개편 케이스: 본문 컨테이너 후보. 상단 판매처 로고/프로필 영역은 제외한다.
    container_patterns = [
        r'<div[^>]*\bclass=[\"\'][^\"\']*(?:board-view-content|view-content|content-detail|fr-view|se-viewer)[^\"\']*[\"\'][^>]*>([\s\S]*?)</div>\s*</div>',
        r'<article[^>]*>([\s\S]*?)</article>',
    ]
    for pattern in container_patterns:
        for body_m in re.finditer(pattern, detail_html, re.I):
            yield trim_to_after_price_area(html.unescape(body_m.group(1)))

    # 3) 컨테이너 정규식이 중첩 div에서 짧게 끊기는 경우를 대비해 상세 전체도 가격/배송 이후만 fallback으로 본다.
    yield trim_to_after_price_area(html.unescape(detail_html))


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
        if is_body_image_candidate(candidate) and not is_too_small_image('', candidate):
            return candidate

    return ''


def iter_structured_detail_nodes(detail_html: str):
    scripts = BeautifulSoup(
        detail_html, "html.parser",
        parse_only=SoupStrainer("script", attrs={"type": "application/ld+json"}),
    )
    for script in scripts.find_all("script"):
        try:
            data = json.loads(script.get_text())
        except (ValueError, TypeError):
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if isinstance(node, dict):
                if isinstance(node.get("@graph"), list):
                    nodes.extend(node["@graph"])
                yield node


def extract_buy_link_from_detail(detail_html: str) -> str:
    for node in iter_structured_detail_nodes(detail_html):
        if node.get("@type") != "Product":
            continue
        offers = node.get("offers", [])
        for offer in offers if isinstance(offers, list) else [offers]:
            candidate = str(offer.get("url", "")) if isinstance(offer, dict) else ""
            if urlsplit(candidate).scheme in {"http", "https"}:
                return candidate

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


def extract_registered_at_from_detail(
    detail_html: str, fallback_date_label: str, now: datetime | None = None,
    fallback_datetime: datetime | None = None,
) -> str:
    """상세 작성시각을 추출하되, 상품 행사일/배송일 같은 미래 날짜 오검출은 버린다."""
    try:
        fallback_dt = datetime.strptime(fallback_date_label, '%Y-%m-%d').replace(tzinfo=KST)
    except Exception:
        fallback_dt = None
    now = now or datetime.now(KST)

    # The v2 page exposes the original post time in JSON-LD; visible times are relative.
    for node in iter_structured_detail_nodes(detail_html):
        if node.get("@type") != "DiscussionForumPosting":
            continue
        try:
            candidate = datetime.fromisoformat(str(node.get("datePublished", "")).replace("Z", "+00:00"))
            if candidate.tzinfo is not None and candidate <= now + timedelta(minutes=5):
                return candidate.astimezone(KST).isoformat()
        except ValueError:
            continue

    patterns = [
        r'(20\d{2})[./-](\d{2})[./-](\d{2})\s+(\d{2}):(\d{2})',
        r'(20\d{2})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2})(?::\d{2})?',
    ]
    candidates = []
    for p in patterns:
        for m in re.finditer(p, detail_html):
            try:
                y, mm, dd, hh, mi = map(int, m.groups()[:5])
                candidate = datetime(y, mm, dd, hh, mi, tzinfo=KST)
                if candidate > now + timedelta(minutes=5):
                    continue
                if fallback_dt and candidate.date() != fallback_dt.date():
                    continue
                candidates.append(candidate)
            except Exception:
                pass

    if candidates:
        return candidates[0].isoformat()
    if fallback_datetime is not None:
        return fallback_datetime.isoformat()
    return f"{fallback_date_label}T00:00:00+09:00"


def parse_count(text: str) -> int:
    value = clean(text).lower().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([k천만]?)", value)
    if not match:
        return 0
    return int(float(match.group(1)) * {"": 1, "k": 1000, "천": 1000, "만": 10000}[match.group(2)])


def parse_list_items(page_html: str, seen=None):
    soup = BeautifulSoup(page_html, "html.parser")
    rows = soup.select(".v2-list > .v2-list-row, tr")
    items = []
    if seen is None:
        seen = set()

    for row in rows:
        title_node = row.select_one("a.subject-link[href]")
        if title_node is None:
            continue
        rel_link = str(title_node.get("href", ""))
        link_m = re.fullmatch(r'(?:https?://(?:www\.)?quasarzone\.com)?/bbs/qb_saleinfo/views/(\d+)(?:\?[^#]*)?', rel_link)
        if not link_m:
            continue

        post_id = link_m.group(1)
        if post_id in seen:
            continue
        comment_node = row.select_one(".ctn-count")
        comments = parse_count(comment_node.get_text() if comment_node is not None else "")
        for comment in title_node.select(".board-list-comment"):
            comment.decompose()
        title = clean(title_node.get_text(" ", strip=True))
        if not title or is_blinded_item({"title": title}):
            continue
        if "공지" in str(row)[:400] or "핫딜 게시판 규정" in title:
            continue

        def text_at(selector, default=""):
            node = row.select_one(selector)
            return clean(node.get_text(" ", strip=True)) if node is not None else default

        category = text_at(".v2-badge, .category", "기타")
        price = clean_price(text_at(".v2-list-row__price, .text-orange", "가격 정보 확인"))
        counts = row.select(".count")
        views = parse_count(text_at(".qc-count-hit") or (counts[-1].get_text() if counts else ""))

        # 퀘이사는 현재 신뢰 가능한 추천 점수를 제공하지 않으므로 온도 계산에서 추천 가중치를 쓰지 않는다.
        likes = 0

        time_text = text_at(".v2-list-row__time, .date")
        if not time_text:
            continue

        img = ''
        # v2 thumbnails use data-preview / CSS backgrounds, not an img element.
        candidates = [str(row.get("data-preview", ""))]
        thumb = row.select_one(".v2-list-row__thumb")
        if thumb is not None:
            background = re.search(r"url\(['\"]?([^)'\"]+)['\"]?\)", str(thumb.get("style", "")))
            if background:
                candidates.append(background.group(1))
        legacy_img = row.select_one("img.maxImg")
        if legacy_img is not None:
            candidates.append(get_img_src_from_tag(str(legacy_img)))
        for src in candidates:
            candidate = normalize_image_url(src)
            if is_body_image_candidate(candidate) and not is_too_small_image('', candidate):
                img = candidate
                break

        seen.add(post_id)
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
            candidate = normalize_image_url(src)
            if not is_body_image_candidate(candidate) or is_too_small_image('', candidate):
                continue
            img = candidate
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


def load_previous_feed() -> Dict:
    if not JSON_PATH.exists():
        return {}
    try:
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_previous_items() -> List[Dict]:
    return list(load_previous_feed().get("items") or [])


def extract_post_id_from_link(link: str) -> str:
    m = re.search(r"/bbs/qb_saleinfo/views/(\d+)", link or "")
    return m.group(1) if m else ""


def has_reusable_detail_fields(item: Dict) -> bool:
    registered_at = (item.get("registeredAt") or "").strip()
    if not registered_at:
        return False
    try:
        if datetime.fromisoformat(registered_at) > datetime.now(KST) + timedelta(minutes=5):
            return False
    except Exception:
        return False
    return bool(
        (item.get("buyLink") or "").strip()
        and ((item.get("desc") or "").strip() or item.get("detailParsed") is True)
    )


def build_previous_detail_lookup(items: List[Dict]) -> Dict[str, Dict]:
    lookup: Dict[str, Dict] = {}
    image_counts = Counter(
        str(item.get("img") or "").strip()
        for item in items or []
        if str(item.get("img") or "").strip()
    )
    repeated_images = {img for img, count in image_counts.items() if count >= 3}
    for item in items or []:
        if not has_reusable_detail_fields(item):
            continue
        if str(item.get("img") or "").strip() in repeated_images:
            # 과거 목록 썸네일/placeholder가 여러 상세에 잘못 캐시된 경우 상세를 다시 열어 본문 이미지를 재추출한다.
            continue
        item_id = str(item.get("id") or "").strip()
        source_link = str(item.get("sourceLink") or "").strip()
        post_id = item_id or extract_post_id_from_link(source_link)
        if post_id:
            lookup[f"id:{post_id}"] = item
        if source_link:
            lookup[f"source:{normalize_source_link(source_link)}"] = item
    return lookup


def build_previous_link_keys(items: List[Dict]) -> set:
    keys = set()
    for item in items or []:
        item_id = str(item.get("id") or "").strip()
        source_link = str(item.get("sourceLink") or "").strip()
        post_id = item_id or extract_post_id_from_link(source_link)
        if post_id:
            keys.add(f"id:{post_id}")
        if source_link:
            keys.add(f"source:{normalize_source_link(source_link)}")
    return keys


def row_exists_in_previous(row: Dict, previous_keys: set) -> bool:
    post_id = str(row.get("id") or "").strip() or extract_post_id_from_link(row.get("sourceLink") or "")
    source_link = normalize_source_link(row.get("sourceLink") or "")
    keys = set()
    if post_id:
        keys.add(f"id:{post_id}")
    if source_link:
        keys.add(f"source:{source_link}")
    return bool(keys & previous_keys)


def page_tail_seen_in_previous(rows: List[Dict], previous_keys: set) -> bool:
    if not rows or not previous_keys:
        return False
    sample_size = max(1, INCREMENTAL_TAIL_SAMPLE_SIZE)
    return any(row_exists_in_previous(row, previous_keys) for row in rows[-sample_size:])


def apply_cached_detail_fields(row: Dict, lookup: Dict[str, Dict]) -> bool:
    post_id = str(row.get("id") or "").strip() or extract_post_id_from_link(row.get("sourceLink") or "")
    source_link = normalize_source_link(row.get("sourceLink") or "")
    cached = lookup.get(f"id:{post_id}") if post_id else None
    if not cached and source_link:
        cached = lookup.get(f"source:{source_link}")
    if not cached or not has_reusable_detail_fields(cached):
        return False

    for key in ("img", "buyLink", "desc", "registeredAt", "date"):
        value = (cached.get(key) or "").strip()
        if value:
            row[key] = value
    if cached.get("detailParsed") is True:
        row["detailParsed"] = True
    row["_detailCached"] = True
    return True


def dedupe_items_by_title(items: List[Dict]) -> List[Dict]:
    seen_titles = set()
    deduped = []
    for item in items:
        title_key = re.sub(r'\s+', ' ', str(item.get('title') or '').strip()).lower()
        if title_key and title_key in seen_titles:
            continue
        if title_key:
            seen_titles.add(title_key)
        deduped.append(item)
    return deduped


def is_blinded_item(item: Dict) -> bool:
    title = clean(str(item.get("title") or "")).lower()
    return "블라인드 처리된 글" in title


def main():
    now = datetime.now(KST)
    since = now - timedelta(hours=48)
    previous_feed = load_previous_feed()
    previous_items = [item for item in previous_feed.get("items", []) if not is_blinded_item(item)]
    expired_ids = {str(value) for value in previous_feed.get("expiredPostIds", [])}
    previous_lookup = build_previous_detail_lookup(previous_items)
    previous_keys = build_previous_link_keys(previous_items)
    sess = requests.Session()
    sess.headers.update(HEADERS)

    filtered = []
    seen = set()
    fetch_mode = FETCH_MODE if FETCH_MODE in {"requests", "browser", "hybrid"} else "requests"
    browser = None
    browser_failures = 0
    browser_fallbacks = 0
    browser_fetches = 0
    request_fetches = 0
    jina_fetches = 0
    last_transport = ""
    list_fetches = 0
    detail_fetches = 0
    cached_details = 0

    def ensure_browser():
        nonlocal browser
        if browser is None:
            try:
                from quasar_browser_fetch import QuasarBrowserFetcher
            except ModuleNotFoundError:
                from scripts.quasar_browser_fetch import QuasarBrowserFetcher
            try:
                browser = QuasarBrowserFetcher().start()
                print("QUASAR_BROWSER_START mode=playwright-chrome")
            except Exception:
                raise
        return browser

    def fetch_requests_html(url: str, timeout: int) -> str:
        nonlocal last_transport, request_fetches
        request_fetches += 1
        response = sess.get(url, timeout=timeout)
        if response.status_code in {403, 429, 430}:
            raise RuntimeError(f"Quasar request blocked ({response.status_code})")
        response.raise_for_status()
        last_transport = "requests"
        return response.text

    def fetch_browser_html(url: str, timeout: int) -> str:
        nonlocal browser_failures, browser_fetches, last_transport
        browser_fetches += 1
        try:
            html_text = ensure_browser().get_html(url, timeout_seconds=timeout)
            last_transport = "browser"
            return html_text
        except Exception:
            browser_failures += 1
            raise

    def fetch_source_html(url: str, request_timeout: int = 25, browser_timeout: int = 45) -> str:
        nonlocal browser_fallbacks
        if fetch_mode == "browser":
            try:
                return fetch_browser_html(url, browser_timeout)
            except Exception as exc:
                if getattr(exc, "blocked", False):
                    raise
                print(f"WARN_QUASAR_BROWSER_REQUEST reason={exc} url={url}")
                return fetch_requests_html(url, request_timeout)

        if fetch_mode == "hybrid":
            try:
                return fetch_requests_html(url, request_timeout)
            except Exception as exc:
                browser_fallbacks += 1
                print(f"QUASAR_BROWSER_FALLBACK reason=request_failed error={exc} url={url}")
                return fetch_browser_html(url, browser_timeout)

        return fetch_requests_html(url, request_timeout)

    def retry_in_browser(url: str, reason: str, timeout: int = 45) -> str:
        nonlocal browser_fallbacks
        if fetch_mode != "hybrid" or last_transport == "browser":
            return ""
        browser_fallbacks += 1
        print(f"QUASAR_BROWSER_FALLBACK reason={reason} url={url}")
        return fetch_browser_html(url, timeout)

    def fetch_jina_html(url: str, timeout: int) -> str:
        nonlocal jina_fetches
        jina_fetches += 1
        response = sess.get(to_jina_url(url), timeout=timeout)
        response.raise_for_status()
        if re.search(r"^(?:Title: Just a moment|Warning: Target URL returned error [45]\d\d)", response.text, re.M):
            raise RuntimeError("Quasar Jina response contains an upstream block/error page")
        return response.text

    print(f"QUASAR_FETCH_MODE {fetch_mode}{' requests-first' if fetch_mode == 'hybrid' else ''}")

    try:
        for page in range(1, MAX_PAGES + 1):
            page_url = LIST_URL if page == 1 else f"{LIST_URL}?page={page}"
            list_fetches += 1
            browsers_before = browser_fetches
            rows = []
            try:
                html_text = fetch_source_html(page_url)
                rows = parse_list_items(html_text, seen)
            except Exception as exc:
                print(f"WARN_QUASAR_LIST_FETCH reason={exc} url={page_url}")
            if not rows and fetch_mode == "hybrid" and browser_fetches == browsers_before:
                try:
                    browser_text = retry_in_browser(page_url, "list_parse_empty")
                    rows = parse_list_items(browser_text, seen) if browser_text else []
                except Exception as exc:
                    print(f"WARN_QUASAR_BROWSER_LIST_PARSE reason={exc} url={page_url}")
            if not rows:
                try:
                    jina_text = fetch_jina_html(page_url, 45)
                    rows = parse_jina_list_items(jina_text, seen)
                except Exception as exc:
                    print(f"WARN_QUASAR_JINA_LIST_FETCH reason={exc} url={page_url}")
            rows = [row for row in rows if not is_blinded_item(row)]
            if not rows:
                raise RuntimeError(f"Quasar list returned no usable rows on page {page}; previous feed preserved")

            old_count = 0
            for row in rows:
                if row["id"] in expired_ids:
                    old_count += 1
                    continue
                try:
                    dt = parse_time_to_datetime(row.get("time", ""), now)
                except ValueError as exc:
                    print(f"WARN_QUASAR_INVALID_TIME id={row['id']} reason={exc}")
                    continue
                date_label = dt.strftime("%Y-%m-%d")
                if dt < since and dt.date() != since.date():
                    expired_ids.add(row["id"])
                    old_count += 1
                    continue

                if apply_cached_detail_fields(row, previous_lookup):
                    cached_details += 1
                    row["commentSignalScore"] = 0
                    row["positiveCommentSignals"] = 0
                    row["negativeCommentSignals"] = 0
                    row["qualitySignalParserVersion"] = QUALITY_SIGNAL_PARSER_VERSION
                    try:
                        registered_dt = datetime.fromisoformat(row["registeredAt"])
                    except Exception:
                        registered_dt = dt
                    if registered_dt < since:
                        expired_ids.add(row["id"])
                        old_count += 1
                        continue
                    row["date"] = registered_dt.strftime("%Y-%m-%d")
                    row.pop("_detailViaJina", None)
                    row.pop("_detailCached", None)
                    filtered.append(row)
                    continue

                detail_html = ""
                try:
                    if NEW_DETAIL_DELAY_SECONDS:
                        jitter = random.uniform(0, min(1.0, NEW_DETAIL_DELAY_SECONDS))
                        time.sleep(NEW_DETAIL_DELAY_SECONDS + jitter)
                    detail_fetches += 1
                    if row.get("_detailViaJina"):
                        detail_html = fetch_jina_html(row["sourceLink"], 25)
                    else:
                        detail_html = fetch_source_html(row["sourceLink"])
                        has_timestamp = re.search(r'20\d{2}[./-]\d{2}[./-]\d{2}[T\s]+\d{2}:\d{2}', detail_html)
                        if (
                            fetch_mode == "hybrid"
                            and last_transport != "browser"
                            and not extract_buy_link_from_detail(detail_html)
                            and not has_timestamp
                        ):
                            browser_text = retry_in_browser(row["sourceLink"], "detail_parse_incomplete")
                            if browser_text:
                                detail_html = browser_text
                                has_timestamp = re.search(
                                    r'20\d{2}[./-]\d{2}[./-]\d{2}[T\s]+\d{2}:\d{2}',
                                    detail_html,
                                )
                        if not extract_buy_link_from_detail(detail_html) and not has_timestamp:
                            detail_html = fetch_jina_html(row["sourceLink"], 25)
                    real_link = extract_buy_link_from_detail(detail_html)
                    body_img = extract_body_image_from_detail(detail_html)
                    row["buyLink"] = real_link or row["sourceLink"]
                    row["desc"] = extract_body_text_from_detail(detail_html)
                    row["detailParsed"] = bool(re.search(r'<textarea[^>]+id=[\"\']org_contents[\"\']', detail_html, re.I))
                    comment_quality = analyze_comment_quality(extract_comment_signal_text(detail_html))
                    row["commentSignalScore"] = comment_quality["score"]
                    row["positiveCommentSignals"] = comment_quality["positiveCount"]
                    row["negativeCommentSignals"] = comment_quality["negativeCount"]
                    row["qualitySignalParserVersion"] = QUALITY_SIGNAL_PARSER_VERSION
                    if body_img:
                        row["img"] = body_img
                    if 'quasarzone.com/' in row["buyLink"] and '/bbs/qb_saleinfo/views/' not in row["buyLink"]:
                        row["buyLink"] = row["sourceLink"]
                except Exception as exc:
                    print(f"WARN_QUASAR_DETAIL_FETCH id={row['id']} reason={exc}")
                    row["buyLink"] = row["sourceLink"]

                row["date"] = date_label
                try:
                    row["registeredAt"] = extract_registered_at_from_detail(
                        detail_html, date_label, now=now, fallback_datetime=dt,
                    )
                except Exception:
                    row["registeredAt"] = dt.isoformat()

                try:
                    registered_dt = datetime.fromisoformat(row["registeredAt"])
                except Exception:
                    registered_dt = dt
                if registered_dt < since:
                    # Date-only list labels otherwise re-fetch the same expired detail every run.
                    expired_ids.add(row["id"])
                    old_count += 1
                    continue
                if registered_dt > now + timedelta(minutes=5):
                    continue

                row["date"] = registered_dt.strftime("%Y-%m-%d")
                row.pop("_detailViaJina", None)
                filtered.append(row)

            if old_count == len(rows):
                break
            if rows and page_tail_seen_in_previous(rows, previous_keys):
                print(f"QUASAR_INCREMENTAL_STOP reason=page_tail_seen page={page} sample={max(1, INCREMENTAL_TAIL_SAMPLE_SIZE)}")
                break
    finally:
        if browser is not None:
            browser.close()
        print(
            "QUASAR_FETCH_SUMMARY "
            f"mode={fetch_mode} lists={list_fetches} details={detail_fetches} cached={cached_details} "
            f"requests={request_fetches} browser={browser_fetches} browser_fallbacks={browser_fallbacks} "
            f"browser_failures={browser_failures} jina={jina_fetches}"
        )

    filtered = dedupe_items_by_title(filtered)
    if not filtered:
        raise RuntimeError("Quasar feed has no valid recent rows; previous feed preserved")

    today_label = str(now.date())
    yesterday_label = str((now - timedelta(days=1)).date())
    today_items = [item for item in filtered if item.get("date") == today_label]
    yesterday_items = [item for item in filtered if item.get("date") == yesterday_label]

    out = {
        "source": LIST_URL,
        "sourceKey": "quasar",
        "partialSnapshot": PARTIAL_SNAPSHOT,
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
        "expiredPostIds": sorted(expired_ids & seen),
        "grouped": {"today": today_items, "yesterday": yesterday_items},
    }

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    staged_path = JSON_PATH.with_suffix(".json.tmp")
    staged_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    staged_path.replace(JSON_PATH)
    print(f"saved: {JSON_PATH} ({len(filtered)} items)")


if __name__ == "__main__":
    main()
