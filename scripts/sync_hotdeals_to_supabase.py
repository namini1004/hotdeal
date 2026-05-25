#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

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
        "?select=source,source_link,buy_link,title,desc,price,category,img,area,dist,time,views,comments,date,registered_at,updated_at"
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
    for row in rows:
        key = f"{row['source']}::{row['source_link']}"
        prev = existing_map.get(key)
        if not prev:
            row["updated_at"] = now_iso
            changed_rows.append(row)
            continue

        if row_changed(row, prev):
            row["updated_at"] = now_iso
            changed_rows.append(row)

    if not changed_rows:
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

    print(f"UPSERT_OK total={written}")


if __name__ == "__main__":
    main()
