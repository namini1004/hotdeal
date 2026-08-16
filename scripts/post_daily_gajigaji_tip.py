#!/usr/bin/env python3
"""Research, validate, and post one original daily Gajigaji shopping tip."""
from __future__ import annotations

import argparse
import contextlib
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / ".artifacts"
API_BASE = "https://gaji.run/api/board-posts"
AUTHOR = "가지딜"
KST = timezone(timedelta(hours=9))
SOURCE_MAX_AGE_DAYS = int(os.environ.get("GAJI_TIP_SOURCE_MAX_AGE_DAYS", "60"))
PRODUCT_COOLDOWN_DAYS = int(os.environ.get("GAJI_TIP_PRODUCT_COOLDOWN_DAYS", "120"))
CODEX_TIMEOUT_SECONDS = int(os.environ.get("GAJI_TIP_CODEX_TIMEOUT_SECONDS", "900"))
TITLE_SIMILARITY_LIMIT = float(os.environ.get("GAJI_TIP_TITLE_SIMILARITY_LIMIT", "0.72"))
BODY_SIMILARITY_LIMIT = float(os.environ.get("GAJI_TIP_BODY_SIMILARITY_LIMIT", "0.70"))
DEFAULT_CODEX_PATH = Path.home() / ".codex" / ".sandbox-bin" / "codex.exe"

GENERIC_PRODUCT_TERMS = {
    "가정용",
    "기기",
    "미니",
    "무선",
    "생활",
    "세트",
    "스마트",
    "용품",
    "유선",
    "제품",
    "핸디",
    "휴대용",
}

SOURCE_CHANNELS = (
    ("노써치", "UCvlSrxnx0enAAquKAg6yy_w"),
    ("귀곰", "UCiTGSmGgJtKTcjEvDk_zRhw"),
    ("ITSub잇섭", "UCdUcjkyZtf-1WJyPPiETF1g"),
    ("정가거부", "UC1KHW0JH7zToxC2H69axgzw"),
)

BLOCKED_SOURCE_PATTERN = re.compile(
    r"주식|증권|코인|가상자산|대출|보험|부동산|계좌\s*(?:개설|만들)|정치|선거",
    re.IGNORECASE,
)
DATE_SUFFIX_PATTERN = re.compile(r"\s*[\[(]?(?:20\d{6}|20\d{2}[./-]\d{1,2}[./-]\d{1,2})[\])]?$", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
BOARD_MARKER_PATTERN = re.compile(r"^<!--gaji-category:(?:tips|mydeals)-->\s*", re.IGNORECASE)

ATOM_NS = "http://www.w3.org/2005/Atom"
MEDIA_NS = "http://search.yahoo.com/mrss/"

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["drafts"],
    "properties": {
        "drafts": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "product", "body", "source_url"],
                "properties": {
                    "title": {"type": "string"},
                    "product": {"type": "string"},
                    "body": {"type": "string"},
                    "source_url": {"type": "string"},
                },
            },
        }
    },
}


@dataclass(frozen=True)
class SourceCandidate:
    channel: str
    title: str
    url: str
    published_at: datetime
    thumbnail_url: str
    description: str = ""

    def prompt_value(self) -> dict:
        return {
            "channel": self.channel,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "description": compact_text(self.description)[:700],
        }


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def request_bytes(url: str, *, method: str = "GET", payload=None, headers=None, timeout: int = 45):
    data = None
    request_headers = {
        "Accept": "*/*",
        "User-Agent": "gajigaji-daily-tip/2.0 (+https://gaji.run)",
        **(headers or {}),
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), response.headers


def request_json(url: str, *, method: str = "GET", payload=None):
    raw, _ = request_bytes(url, method=method, payload=payload, headers={"Accept": "application/json"})
    return json.loads(raw.decode("utf-8") or "{}")


def fetch_existing_posts() -> list[dict]:
    payload = request_json(f"{API_BASE}?limit=100&_ts={int(time.time())}")
    return [item for item in (payload.get("items") or []) if item.get("category") == "tips"]


def parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def strip_board_markup(value: str) -> str:
    text = BOARD_MARKER_PATTERN.sub("", str(value or "")).strip()
    text = re.sub(r"\n## 참고 자료\s*\n.*$", "", text, flags=re.DOTALL)
    return text.strip()


def normalize_similarity_text(value: str) -> str:
    text = strip_board_markup(value).lower()
    text = DATE_SUFFIX_PATTERN.sub("", text)
    text = URL_PATTERN.sub(" ", text)
    text = re.sub(r"[#*_`~>|\[\](){},.!?:;'\"/\\+-]", " ", text)
    return compact_text(text)


def text_similarity(left: str, right: str) -> float:
    a = normalize_similarity_text(left)
    b = normalize_similarity_text(right)
    if not a or not b:
        return 0.0
    sequence_score = difflib.SequenceMatcher(None, a, b).ratio()
    a_tokens = set(re.findall(r"[0-9a-z가-힣]{2,}", a))
    b_tokens = set(re.findall(r"[0-9a-z가-힣]{2,}", b))
    union = a_tokens | b_tokens
    token_score = len(a_tokens & b_tokens) / len(union) if union else 0.0
    return max(sequence_score, token_score)


def source_urls_from_posts(posts: Iterable[dict]) -> set[str]:
    urls: set[str] = set()
    for post in posts:
        urls.update(match.rstrip(".,") for match in URL_PATTERN.findall(str(post.get("body") or "")))
    return urls


def has_automation_post_today(posts: Iterable[dict], now: datetime) -> bool:
    today = now.astimezone(KST).date()
    for post in posts:
        if str(post.get("author") or "").strip() not in {AUTHOR, "가지가지"}:
            continue
        created_at = parse_datetime(post.get("createdAt") or post.get("created_at") or "")
        if created_at and created_at.astimezone(KST).date() == today:
            return True
    return False


def parse_youtube_feed(channel: str, channel_id: str, now: datetime) -> list[SourceCandidate]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    raw, _ = request_bytes(url, headers={"Accept": "application/atom+xml, application/xml"})
    root = ElementTree.fromstring(raw)
    cutoff = now.astimezone(timezone.utc) - timedelta(days=SOURCE_MAX_AGE_DAYS)
    candidates: list[SourceCandidate] = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        title = compact_text(entry.findtext(f"{{{ATOM_NS}}}title") or "")
        published_at = parse_datetime(entry.findtext(f"{{{ATOM_NS}}}published") or "")
        link_node = entry.find(f"{{{ATOM_NS}}}link")
        media_group = entry.find(f"{{{MEDIA_NS}}}group")
        thumbnail_node = media_group.find(f"{{{MEDIA_NS}}}thumbnail") if media_group is not None else None
        description = media_group.findtext(f"{{{MEDIA_NS}}}description") if media_group is not None else ""
        item_url = str(link_node.attrib.get("href") if link_node is not None else "").strip()
        thumbnail_url = str(thumbnail_node.attrib.get("url") if thumbnail_node is not None else "").strip()
        if not title or not published_at or not item_url or not thumbnail_url:
            continue
        if published_at.astimezone(timezone.utc) < cutoff:
            continue
        if BLOCKED_SOURCE_PATTERN.search(title):
            continue
        candidates.append(
            SourceCandidate(
                channel=channel,
                title=title,
                url=item_url,
                published_at=published_at,
                thumbnail_url=thumbnail_url,
                description=description or "",
            )
        )
    return candidates


def collect_source_candidates(posts: Iterable[dict], now: datetime) -> list[SourceCandidate]:
    used_urls = source_urls_from_posts(posts)
    candidates: list[SourceCandidate] = []
    errors: list[str] = []
    for channel, channel_id in SOURCE_CHANNELS:
        try:
            channel_candidates = parse_youtube_feed(channel, channel_id, now)
        except Exception as exc:
            errors.append(f"{channel}:{type(exc).__name__}")
            continue
        candidates.extend(item for item in channel_candidates[:10] if item.url not in used_urls)

    unique: dict[str, SourceCandidate] = {}
    for candidate in sorted(candidates, key=lambda item: item.published_at, reverse=True):
        unique.setdefault(candidate.url, candidate)
    result = list(unique.values())
    if not result:
        detail = ",".join(errors) if errors else "all recent source URLs were already used"
        raise RuntimeError(f"No usable trusted source candidates: {detail}")
    return result


def build_generation_prompt(posts: list[dict], candidates: list[SourceCandidate]) -> str:
    existing_titles = [compact_text(post.get("title") or "") for post in posts if post.get("title")]
    source_payload = [candidate.prompt_value() for candidate in candidates]
    return f"""당신은 gaji.run의 '가지가지' 메뉴에 매일 한 편의 실용적인 쇼핑 팁을 쓰는 편집자입니다.

아래 신뢰 목록은 공식 YouTube 채널 RSS에서 오늘 수집한 최근 콘텐츠입니다. 반드시 이 목록에서 서로 다른 source_url 3개를 골라, 각 자료의 제품이나 구매 판단 포인트를 일반 소비자가 바로 쓸 수 있는 독립적인 원고 후보 3개로 바꾸세요.

기존 제목:
{json.dumps(existing_titles, ensure_ascii=False, indent=2)}

사용 가능한 출처:
{json.dumps(source_payload, ensure_ascii=False, indent=2)}

작성 규칙:
- 모든 문장은 자연스러운 한국어로 씁니다.
- 각 source_url은 위 목록의 URL과 글자까지 정확히 같아야 합니다.
- 후보 3개는 제품군과 관점이 서로 달라야 합니다.
- 기존 제목과 같은 제품·주장·문장 구조를 반복하지 않습니다.
- 제목에는 날짜, 출처명, 영상 제목 복사, 광고성 과장을 넣지 않습니다.
- 일시적 할인 가격을 그대로 소개하지 말고 오래 쓸 수 있는 구매 기준으로 바꿉니다.
- 투자·의료·법률 조언은 쓰지 않습니다.
- 본문은 500~900자 정도로, 첫 줄은 '# 제목'이어야 합니다.
- 짧은 문제 제기, 생활 체감 중심 설명, '구매 전 체크:' bullet 4~6개, 마지막 '한 줄 팁:'을 포함합니다.
- 출처 링크나 '참고 자료' 구역은 본문에 직접 쓰지 마세요. 검증 후 시스템이 붙입니다.
- 출처 제목만으로 확인할 수 없는 숫자나 단정적인 사실을 만들지 않습니다.
- product는 중복 검사에 쓸 짧고 일반적인 제품군 이름으로 씁니다.

JSON 스키마에 맞는 후보 3개만 반환하세요."""


def find_codex_path(explicit_path: str = "") -> Path:
    candidates = [
        Path(explicit_path) if explicit_path else None,
        Path(os.environ["GAJI_CODEX_PATH"]) if os.environ.get("GAJI_CODEX_PATH") else None,
        DEFAULT_CODEX_PATH,
        Path(shutil.which("codex")) if shutil.which("codex") else None,
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise RuntimeError("Codex CLI was not found. Set GAJI_CODEX_PATH to an executable codex CLI.")


def parse_json_output(raw: str) -> dict:
    value = str(raw or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE | re.DOTALL)
    return json.loads(value)


def generate_drafts(prompt: str, codex_path: Path) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="gajigaji-tip-") as temp_dir:
        temp_path = Path(temp_dir)
        schema_path = temp_path / "output-schema.json"
        output_path = temp_path / "output.json"
        schema_path.write_text(json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8")
        args = [
            str(codex_path),
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "-C",
            str(temp_path),
            "--color",
            "never",
            "-c",
            'model_reasoning_effort="low"',
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "-",
        ]
        env = os.environ.copy()
        env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"})
        completed = subprocess.run(
            args,
            cwd=temp_path,
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=CODEX_TIMEOUT_SECONDS,
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            detail = compact_text(completed.stderr)[-2000:]
            raise RuntimeError(f"Codex generation failed ({completed.returncode}): {detail}")
        raw = output_path.read_text(encoding="utf-8") if output_path.exists() else completed.stdout
        payload = parse_json_output(raw)
        drafts = payload.get("drafts") or []
        if len(drafts) != 3:
            raise RuntimeError(f"Codex returned {len(drafts)} drafts instead of 3")
        return drafts


def recent_product_conflict(product: str, posts: Iterable[dict], now: datetime) -> str:
    product_key = normalize_similarity_text(product).replace(" ", "")
    if len(product_key) < 2:
        return "invalid_product"
    product_terms = {
        term
        for term in re.findall(r"[0-9a-z가-힣]{2,}", normalize_similarity_text(product))
        if term not in GENERIC_PRODUCT_TERMS
    }
    for modifier in GENERIC_PRODUCT_TERMS:
        if product_key.startswith(modifier) and len(product_key) - len(modifier) >= 2:
            product_terms.add(product_key[len(modifier) :])
    cutoff = now.astimezone(timezone.utc) - timedelta(days=PRODUCT_COOLDOWN_DAYS)
    for post in posts:
        created_at = parse_datetime(post.get("createdAt") or post.get("created_at") or "")
        if created_at and created_at.astimezone(timezone.utc) < cutoff:
            continue
        title_key = normalize_similarity_text(post.get("title") or "").replace(" ", "")
        if (
            product_key in title_key
            or title_key in product_key
            or any(term in title_key for term in product_terms)
        ):
            return compact_text(post.get("title") or "")
    return ""


def validate_draft(
    draft: dict,
    posts: list[dict],
    source_map: dict[str, SourceCandidate],
    now: datetime,
) -> list[str]:
    title = compact_text(draft.get("title") or "")
    body = strip_board_markup(draft.get("body") or "")
    product = compact_text(draft.get("product") or "")
    source_url = str(draft.get("source_url") or "").strip()
    reasons: list[str] = []

    if not 10 <= len(title) <= 70:
        reasons.append("title_length")
    if DATE_SUFFIX_PATTERN.search(title):
        reasons.append("date_suffix")
    if not 450 <= len(body) <= 1300:
        reasons.append("body_length")
    if URL_PATTERN.search(body):
        reasons.append("unexpected_body_url")
    if source_url not in source_map:
        reasons.append("untrusted_source")
    if source_url in source_urls_from_posts(posts):
        reasons.append("source_already_used")

    for post in posts:
        existing_title = post.get("title") or ""
        if text_similarity(title, existing_title) >= TITLE_SIMILARITY_LIMIT:
            reasons.append(f"similar_title:{compact_text(existing_title)[:60]}")
            break
    for post in posts:
        existing_body = post.get("body") or ""
        if len(strip_board_markup(existing_body)) < 100:
            continue
        if text_similarity(body, existing_body) >= BODY_SIMILARITY_LIMIT:
            reasons.append(f"similar_body:{compact_text(post.get('title') or '')[:60]}")
            break

    product_conflict = recent_product_conflict(product, posts, now)
    if product_conflict:
        reasons.append(f"product_cooldown:{product_conflict}")
    return reasons


def pick_valid_draft(
    drafts: list[dict],
    posts: list[dict],
    candidates: list[SourceCandidate],
    now: datetime,
) -> tuple[dict, SourceCandidate, list[dict]]:
    source_map = {candidate.url: candidate for candidate in candidates}
    rejected: list[dict] = []
    chosen_sources: set[str] = set()
    for draft in drafts:
        source_url = str(draft.get("source_url") or "").strip()
        reasons = validate_draft(draft, posts, source_map, now)
        if source_url in chosen_sources:
            reasons.append("duplicate_generated_source")
        if reasons:
            rejected.append({"title": compact_text(draft.get("title") or "")[:80], "reasons": reasons})
            continue
        chosen_sources.add(source_url)
        return draft, source_map[source_url], rejected
    raise RuntimeError(f"All generated drafts were rejected: {json.dumps(rejected, ensure_ascii=False)}")


def validate_image_url(url: str) -> bool:
    try:
        raw, headers = request_bytes(
            url,
            headers={"Accept": "image/avif,image/webp,image/png,image/jpeg,*/*", "Range": "bytes=0-4095"},
            timeout=30,
        )
    except Exception:
        return False
    content_type = str(headers.get("Content-Type") or "").lower()
    return content_type.startswith("image/") and len(raw) >= 64


def prepare_body(title: str, body: str, source: SourceCandidate) -> str:
    clean = strip_board_markup(body)
    lines = clean.splitlines()
    if lines and lines[0].strip().startswith("#"):
        lines[0] = f"# {title}"
    else:
        lines = [f"# {title}", "", *lines]
    clean = "\n".join(lines).strip()
    reference = f"## 참고 자료\n- [{source.channel}: {source.title}]({source.url})"
    return f"<!--gaji-category:tips-->\n{clean}\n\n{reference}"


def build_payload(draft: dict, source: SourceCandidate) -> dict:
    title = compact_text(draft.get("title") or "")
    return {
        "title": title,
        "body": prepare_body(title, draft.get("body") or "", source),
        "category": "tips",
        "img": source.thumbnail_url,
        "author": AUTHOR,
    }


@contextlib.contextmanager
def single_run_lock():
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = ARTIFACTS_DIR / "gajigaji_daily_tip.lock"
    if lock_path.exists() and time.time() - lock_path.stat().st_mtime > CODEX_TIMEOUT_SECONDS + 600:
        lock_path.unlink(missing_ok=True)
    try:
        handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError("Another Gajigaji daily tip run is already active") from exc
    try:
        os.write(handle, f"pid={os.getpid()} started={datetime.now(timezone.utc).isoformat()}".encode("ascii"))
        os.close(handle)
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-today-check", action="store_true")
    parser.add_argument("--codex-path", default="")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    with single_run_lock():
        posts = fetch_existing_posts()
        if not args.skip_today_check and has_automation_post_today(posts, now):
            print(json.dumps({"posted": False, "skipped": "already_posted_today"}, ensure_ascii=False))
            return 0

        candidates = collect_source_candidates(posts, now)
        codex_path = find_codex_path(args.codex_path)
        drafts = generate_drafts(build_generation_prompt(posts, candidates), codex_path)
        draft, source, rejected = pick_valid_draft(drafts, posts, candidates, now)
        if not validate_image_url(source.thumbnail_url):
            raise RuntimeError(f"Source image validation failed: {source.thumbnail_url}")
        payload = build_payload(draft, source)

        if args.dry_run:
            print(
                json.dumps(
                    {
                        "dryRun": True,
                        "title": payload["title"],
                        "product": compact_text(draft.get("product") or ""),
                        "source": {"channel": source.channel, "title": source.title, "url": source.url},
                        "img": payload["img"],
                        "bodyLength": len(payload["body"]),
                        "body": payload["body"],
                        "rejected": rejected,
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        latest_posts = fetch_existing_posts()
        if has_automation_post_today(latest_posts, datetime.now(timezone.utc)):
            print(json.dumps({"posted": False, "skipped": "already_posted_today_after_generation"}, ensure_ascii=False))
            return 0
        final_reasons = validate_draft(draft, latest_posts, {source.url: source}, datetime.now(timezone.utc))
        if final_reasons:
            raise RuntimeError(f"Draft failed final duplicate check: {final_reasons}")

        result = request_json(API_BASE, method="POST", payload=payload)
        item = result.get("item") or {}
        if item.get("title") != payload["title"] or not item.get("img"):
            raise RuntimeError(f"Posted item verification failed: {json.dumps(item, ensure_ascii=False)[:1000]}")
        print(
            json.dumps(
                {
                    "posted": True,
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "product": compact_text(draft.get("product") or ""),
                    "source": {"channel": source.channel, "title": source.title, "url": source.url},
                    "img": item.get("img"),
                    "rejected": rejected,
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, subprocess.TimeoutExpired, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"GAJIGAJI_TIP_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
