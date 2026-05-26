#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict
from urllib.parse import quote

import requests

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
    "area",
    "dist",
    "time",
    "views",
    "comments",
    "date",
    "registered_at",
]


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


def fetch_existing_map(supabase_url: str, service_key: str) -> Dict[str, Dict]:
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    endpoint = (
        f"{supabase_url}/rest/v1/deals"
        "?select=source,source_link,buy_link,title,desc,price,category,img,area,dist,time,views,comments,date,registered_at,updated_at,deleted_at"
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
