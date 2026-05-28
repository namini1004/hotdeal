#!/usr/bin/env python3
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import parse_qs, quote, urlparse

import requests
try:
    from PIL import Image, ImageOps
except ModuleNotFoundError:
    import subprocess
    import sys

    subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow"])
    from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
FEED_FILES = [
    ROOT / "assets" / "ppomppu_hotdeals_2days.json",
    ROOT / "assets" / "quasar_hotdeals_2days.json",
    ROOT / "assets" / "fmkorea_hotdeals_2days.json",
    ROOT / "assets" / "ruliweb_hotdeals_1day.json",
]

TRACKED_FIELDS = [
    "buy_link",
    "title",
    "desc",
    "price",
    "category",
    "img",
    "detail_img",
    "area",
    "dist",
    "time",
    "views",
    "comments",
    "date",
    "registered_at",
]

IMAGE_BUCKET = os.environ.get("SUPABASE_IMAGE_BUCKET", "deal-images").strip() or "deal-images"
THUMBNAIL_MAX_SIZE = int(os.environ.get("MIRROR_THUMBNAIL_MAX_SIZE", "320"))
DETAIL_IMAGE_MAX_SIZE = int(os.environ.get("MIRROR_DETAIL_IMAGE_MAX_SIZE", "640"))
DETAIL_IMAGE_VARIANT = f"detail{DETAIL_IMAGE_MAX_SIZE}"
THUMBNAIL_WEBP_QUALITY = int(os.environ.get("MIRROR_THUMBNAIL_WEBP_QUALITY", "75"))
DETAIL_IMAGE_WEBP_QUALITY = int(os.environ.get("MIRROR_DETAIL_IMAGE_WEBP_QUALITY", "82"))
IMAGE_HEADERS_BY_SOURCE = {
    "ppomppu": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
        "Referer": "https://m.ppomppu.co.kr/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    },
    "ruliweb": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
        "Referer": "https://m.ruliweb.com/market/board/1020",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    },
}
MAX_MIRROR_IMAGE_BYTES = int(os.environ.get("MAX_MIRROR_IMAGE_BYTES", "3145728"))
_bucket_ready = False


def load_items() -> List[Dict]:
    merged: List[Dict] = []
    for f in FEED_FILES:
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        merged.extend(data.get("items", []))
    return merged


def normalize(item: Dict) -> Dict:
    source = str(item.get("source") or "feed").strip()
    source_link = str(item.get("sourceLink") or "").strip()
    buy_link = str(item.get("buyLink") or source_link).strip()
    return {
        "source": source,
        "source_link": source_link,
        "buy_link": buy_link,
        "title": str(item.get("title") or "제목 없음").strip(),
        "desc": str(item.get("desc") or "").strip(),
        "price": str(item.get("price") or "").strip(),
        "category": str(item.get("category") or "기타").strip(),
        "img": str(item.get("img") or "").strip(),
        "detail_img": str(item.get("detailImg") or item.get("detail_img") or "").strip(),
        "area": str(item.get("area") or "뽐뿌 핫딜").strip(),
        "dist": str(item.get("dist") or "기타").strip(),
        "time": str(item.get("time") or item.get("date") or "").strip(),
        "views": int(item.get("views") or 0),
        "comments": int(item.get("comments") or 0),
        "date": str(item.get("date") or "").strip(),
        "registered_at": item.get("registeredAt") or None,
        "updated_at": None,
        "deleted_at": None,
    }


def chunked(rows: List[Dict], size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def row_changed(new_row: Dict, old_row: Dict) -> bool:
    for f in TRACKED_FIELDS:
        if (new_row.get(f) or "") != (old_row.get(f) or ""):
            return True
    return False


def storage_public_prefix(supabase_url: str) -> str:
    return f"{supabase_url}/storage/v1/object/public/{IMAGE_BUCKET}/"


def is_storage_image_url(img: str, supabase_url: str) -> bool:
    return str(img or "").startswith(storage_public_prefix(supabase_url))


def decode_proxy_image_url(src: str) -> str:
    raw = str(src or "").strip()
    if raw.startswith("/api/image-proxy?"):
        query = parse_qs(urlparse(raw).query)
        return str((query.get("url") or [""])[0]).strip()
    return raw


def is_reusable_storage_webp(img: str, source: str, supabase_url: str, variant: str = "") -> bool:
    prefix = f"{storage_public_prefix(supabase_url)}{source}/"
    if variant:
        prefix = f"{prefix}"
        if f"-{variant}-" not in str(img or ""):
            return False
    return str(img or "").startswith(prefix) and urlparse(str(img)).path.lower().endswith(".webp")


def row_id_from_source_link(source: str, source_link: str) -> str:
    source_link = source_link or ""
    if source == "ppomppu":
        m = re.search(r"[?&]no=(\d+)", source_link)
        if m:
            return m.group(1)
    if source == "ruliweb":
        m = re.search(r"/read/(\d+)", source_link)
        if m:
            return m.group(1)
    return hashlib.sha1(source_link.encode("utf-8")).hexdigest()[:12]


def is_blocked_image_candidate(source: str, src: str) -> bool:
    src_l = (src or "").lower()
    if not src_l or not src_l.startswith("http"):
        return True
    if source == "ruliweb" and "ruliweb_bi.png" in src_l:
        return True
    blocked_tokens = ["transparent.", "blank.", "noimage", "no_image", "spacer."]
    return any(token in src_l for token in blocked_tokens)


def make_webp_image(content: bytes, max_size: int, quality: Optional[int] = None) -> bytes:
    image = Image.open(io.BytesIO(content))
    image = ImageOps.exif_transpose(image)
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])
        image = background
    else:
        image = image.convert("RGB")
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="WEBP", quality=quality if quality is not None else THUMBNAIL_WEBP_QUALITY, method=6)
    return out.getvalue()


def make_webp_thumbnail(content: bytes) -> bytes:
    return make_webp_image(content, THUMBNAIL_MAX_SIZE, THUMBNAIL_WEBP_QUALITY)


def ensure_public_image_bucket(supabase_url: str, service_key: str):
    global _bucket_ready
    if _bucket_ready:
        return

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    bucket_url = f"{supabase_url}/storage/v1/bucket/{quote(IMAGE_BUCKET, safe='')}"
    res = requests.get(bucket_url, headers=headers, timeout=30)
    if res.status_code == 404 or "Bucket not found" in (res.text or ""):
        create_res = requests.post(
            f"{supabase_url}/storage/v1/bucket",
            headers=headers,
            json={"id": IMAGE_BUCKET, "name": IMAGE_BUCKET, "public": True},
            timeout=30,
        )
        if not create_res.ok and create_res.status_code not in {400, 409}:
            raise RuntimeError(f"Supabase storage bucket create failed ({create_res.status_code}): {create_res.text}")
    elif not res.ok:
        raise RuntimeError(f"Supabase storage bucket check failed ({res.status_code}): {res.text}")

    _bucket_ready = True


def mirror_feed_image(row: Dict, prev: Optional[Dict], supabase_url: str, service_key: str) -> Dict[str, str]:
    """뽐딜/루딜 원본 이미지를 목록용 320px와 상세용 640px WebP로 저장한다."""
    source = str(row.get("source") or "").strip()
    src = decode_proxy_image_url(row.get("img") or "")
    if source not in IMAGE_HEADERS_BY_SOURCE:
        raw_img = str(row.get("img") or "").strip()
        return {"img": raw_img, "detail_img": str(row.get("detail_img") or raw_img).strip()}
    if is_blocked_image_candidate(source, src):
        return {"img": "", "detail_img": ""}
    if is_reusable_storage_webp(src, source, supabase_url):
        return {"img": src, "detail_img": str(row.get("detail_img") or src).strip()}

    prev_img = str((prev or {}).get("img") or "").strip()
    prev_detail_img = str((prev or {}).get("detail_img") or "").strip()
    if is_reusable_storage_webp(prev_img, source, supabase_url, "thumb") and is_reusable_storage_webp(prev_detail_img, source, supabase_url, DETAIL_IMAGE_VARIANT):
        # 같은 게시글은 기존 WebP 썸네일/상세 이미지를 재사용해 원본 CDN 재요청을 최소화한다.
        return {"img": prev_img, "detail_img": prev_detail_img}

    ensure_public_image_bucket(supabase_url, service_key)
    res = requests.get(src, headers=IMAGE_HEADERS_BY_SOURCE[source], timeout=25)
    if not res.ok:
        raise RuntimeError(f"{source} image download failed ({res.status_code})")

    content_type = res.headers.get("content-type") or ""
    if not content_type.lower().startswith("image/"):
        raise RuntimeError(f"{source} image response is not image ({content_type})")
    if len(res.content) < 500:
        raise RuntimeError(f"{source} image response too small")
    if len(res.content) > MAX_MIRROR_IMAGE_BYTES:
        raise RuntimeError(f"{source} image too large ({len(res.content)} bytes)")

    variants = {}
    public_urls = {}
    if is_reusable_storage_webp(prev_img, source, supabase_url, "thumb"):
        public_urls["thumb"] = prev_img
    else:
        variants["thumb"] = make_webp_image(res.content, THUMBNAIL_MAX_SIZE, THUMBNAIL_WEBP_QUALITY)

    if is_reusable_storage_webp(prev_detail_img, source, supabase_url, DETAIL_IMAGE_VARIANT):
        public_urls[DETAIL_IMAGE_VARIANT] = prev_detail_img
    else:
        variants[DETAIL_IMAGE_VARIANT] = make_webp_image(res.content, DETAIL_IMAGE_MAX_SIZE, DETAIL_IMAGE_WEBP_QUALITY)
    digest = hashlib.sha1(src.encode("utf-8")).hexdigest()[:12]
    row_id = row_id_from_source_link(source, row.get("source_link") or "")
    upload_headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "image/webp",
        "Cache-Control": "31536000",
        "x-upsert": "true",
    }
    for variant, body in variants.items():
        object_path = f"{source}/{row_id}-{variant}-{digest}.webp"
        upload_url = f"{supabase_url}/storage/v1/object/{IMAGE_BUCKET}/{object_path}"
        upload_res = requests.post(upload_url, headers=upload_headers, data=body, timeout=60)
        if not upload_res.ok:
            raise RuntimeError(f"Supabase image upload failed ({upload_res.status_code}): {upload_res.text}")
        public_urls[variant] = f"{storage_public_prefix(supabase_url)}{object_path}"

    return {"img": public_urls["thumb"], "detail_img": public_urls[DETAIL_IMAGE_VARIANT]}


def mirror_feed_images(rows: List[Dict], existing_map: Dict[str, Dict], supabase_url: str, service_key: str):
    for row in rows:
        if row.get("source") not in IMAGE_HEADERS_BY_SOURCE:
            continue
        key = f"{row['source']}::{row['source_link']}"
        try:
            mirrored = mirror_feed_image(row, existing_map.get(key), supabase_url, service_key)
            row["img"] = mirrored.get("img", "")
            row["detail_img"] = mirrored.get("detail_img", row["img"])
        except Exception as exc:
            # 이미지 미러링 실패가 피드 전체 갱신 실패로 번지지 않게 기존/원본 URL을 유지한다.
            print(f"WARN_IMAGE_MIRROR_SKIP source={row.get('source')} source_link={row.get('source_link')} reason={exc}")


def fetch_existing_map(supabase_url: str, service_key: str) -> Dict[str, Dict]:
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    endpoint = (
        f"{supabase_url}/rest/v1/deals"
        "?select=source,source_link,buy_link,title,desc,price,category,img,detail_img,area,dist,time,views,comments,date,registered_at,updated_at,deleted_at"
        "&source=neq.user"
    )

    existing: Dict[str, Dict] = {}
    start = 0
    page_size = 1000

    while True:
        end = start + page_size - 1
        page_headers = {**headers, "Range": f"{start}-{end}"}
        res = requests.get(endpoint, headers=page_headers, timeout=60)
        if not res.ok:
            raise SystemExit(f"Supabase read failed ({res.status_code}): {res.text}")

        rows = res.json() or []
        if not rows:
            break

        for row in rows:
            key = f"{row.get('source', '')}::{row.get('source_link', '')}"
            if row.get("source") and row.get("source_link"):
                existing[key] = row

        if len(rows) < page_size:
            break
        start += page_size

    return existing


def send_push_ingest(changed_rows: List[Dict]):
    ingest_url = os.environ.get("PUSH_INGEST_URL", "").strip()
    ingest_secret = os.environ.get("PUSH_INGEST_SECRET", "").strip()
    if not ingest_url or not ingest_secret or not changed_rows:
        return "SKIP"

    rows = [row for row in changed_rows if not row.get("deleted_at")]
    if not rows:
        return "SKIP"

    headers = {
        "Content-Type": "application/json",
        "x-ingest-secret": ingest_secret,
    }
    res = requests.post(
        ingest_url,
        headers=headers,
        json={"rows": rows},
        timeout=60,
    )
    if not res.ok:
        raise SystemExit(f"Push ingest failed ({res.status_code}): {res.text}")
    return "OK"


def main():
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not service_key:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    raw_items = load_items()
    norm_items = [normalize(v) for v in raw_items if (v.get("sourceLink") or "").strip()]

    # source+source_link 기준 중복 제거(최신 항목 우선)
    dedup = {}
    for row in norm_items:
        dedup[f"{row['source']}::{row['source_link']}"] = row
    rows = list(dedup.values())

    if not rows:
        print("NO_ROWS")
        return

    existing_map = fetch_existing_map(supabase_url, service_key)
    mirror_feed_images(rows, existing_map, supabase_url, service_key)
    now_iso = datetime.now(timezone.utc).isoformat()

    changed_rows: List[Dict] = []
    current_keys = set()
    for row in rows:
        key = f"{row['source']}::{row['source_link']}"
        current_keys.add(key)
        prev = existing_map.get(key)
        if not prev:
            row["updated_at"] = now_iso
            changed_rows.append(row)
            continue

        # soft-deleted 되었던 글이 다시 수집되면 즉시 복구
        if prev.get("deleted_at"):
            row["updated_at"] = now_iso
            row["deleted_at"] = None
            changed_rows.append(row)
            continue

        if row_changed(row, prev):
            row["updated_at"] = now_iso
            changed_rows.append(row)

    # 이번 수집 결과에 없는 기존 feed 글은 soft delete 처리
    deleted_rows: List[Dict] = []
    for key, prev in existing_map.items():
        if key in current_keys:
            continue
        if prev.get("deleted_at"):
            continue
        source = str(prev.get("source") or "").strip()
        source_link = str(prev.get("source_link") or "").strip()
        if not source or not source_link:
            continue
        deleted_rows.append(
            {
                "source": source,
                "source_link": source_link,
                "deleted_at": now_iso,
                "updated_at": now_iso,
            }
        )

    if not changed_rows and not deleted_rows:
        print("NO_CHANGE")
        return

    endpoint_upsert = f"{supabase_url}/rest/v1/deals?on_conflict=source,source_link"
    endpoint_insert = f"{supabase_url}/rest/v1/deals"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    written = 0

    # 1) 신규/변경 행은 upsert
    if changed_rows:
        use_insert_fallback = False
        for batch in chunked(changed_rows, 400):
            endpoint = endpoint_insert if use_insert_fallback else endpoint_upsert
            res = requests.post(endpoint, headers=headers, json=batch, timeout=60)
            if not res.ok and (res.status_code == 400 and "42P10" in (res.text or "")):
                use_insert_fallback = True
                headers["Prefer"] = "return=minimal"
                res = requests.post(endpoint_insert, headers=headers, json=batch, timeout=60)

            if not res.ok:
                raise SystemExit(f"Supabase upsert failed ({res.status_code}): {res.text}")
            written += len(batch)

    # 2) 수집에서 사라진 행은 PATCH로 soft delete
    if deleted_rows:
        for row in deleted_rows:
            source = row["source"]
            source_link = row["source_link"]
            patch_endpoint = (
                f"{supabase_url}/rest/v1/deals"
                f"?source=eq.{quote(source, safe='')}"
                f"&source_link=eq.{quote(source_link, safe='')}"
            )
            res = requests.patch(
                patch_endpoint,
                headers={**headers, "Prefer": "return=minimal"},
                json={"deleted_at": row["deleted_at"], "updated_at": row["updated_at"]},
                timeout=60,
            )
            if not res.ok:
                raise SystemExit(f"Supabase soft delete failed ({res.status_code}): {res.text}")
            written += 1

    ingest_status = send_push_ingest(changed_rows)
    print(f"UPSERT_OK total={written} changed={len(changed_rows)} deleted={len(deleted_rows)} ingest={ingest_status}")


if __name__ == "__main__":
    main()
