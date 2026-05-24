#!/usr/bin/env python3
import json
import os
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
        "updated_at": item.get("registeredAt") or None,
        "deleted_at": None,
    }


def chunked(rows: List[Dict], size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


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

    endpoint = f"{supabase_url}/rest/v1/deals?on_conflict=source,source_link"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    written = 0
    for batch in chunked(rows, 400):
        res = requests.post(endpoint, headers=headers, json=batch, timeout=60)
        if not res.ok:
            raise SystemExit(f"Supabase upsert failed ({res.status_code}): {res.text}")
        written += len(batch)

    print(f"UPSERT_OK total={written}")


if __name__ == "__main__":
    main()
