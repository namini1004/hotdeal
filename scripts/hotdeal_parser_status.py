#!/usr/bin/env python3
"""Summarize hotdeal parser health from local artifacts and logs."""
from __future__ import annotations

import json
import re
import urllib.request
import argparse
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "ppomppu": ROOT / "assets" / "ppomppu_hotdeals_2days.json",
    "quasar": ROOT / "assets" / "quasar_hotdeals_2days.json",
    "fmkorea": ROOT / "assets" / "fmkorea_hotdeals_2days.json",
    "ruliweb": ROOT / "assets" / "ruliweb_hotdeals_1day.json",
}
FMKOREA_BACKOFF = ROOT / ".artifacts" / "fmkorea_backoff_state.json"
FMKOREA_LOG = ROOT / ".artifacts" / "logs" / "hotdeal_fmkorea_ingest.log"
PRODUCTION_FEED_URL = "https://gaji.run/api/deals?scope=feed"


def parse_dt(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def age_minutes(value: str):
    dt = parse_dt(value)
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def source_summary(name: str, path: Path):
    data = load_json(path)
    if not data:
        return {
            "source": name,
            "path": str(path),
            "exists": path.exists(),
            "items": 0,
            "generatedAt": "",
            "ageMinutes": None,
            "staleFallback": None,
        }
    generated_at = str(data.get("generatedAt") or "")
    return {
        "source": name,
        "path": str(path),
        "exists": True,
        "items": len(data.get("items") or []),
        "generatedAt": generated_at,
        "ageMinutes": age_minutes(generated_at),
        "staleFallback": data.get("staleFallback"),
    }


def fmkorea_backoff_summary():
    data = load_json(FMKOREA_BACKOFF) or {}
    next_allowed = str(data.get("nextAllowedAt") or "")
    remaining = age_minutes(next_allowed)
    if remaining is not None:
        remaining = max(0, -remaining)
    return {
        "failures": int(data.get("failures") or 0),
        "lastBlockedAt": data.get("lastBlockedAt") or "",
        "lastSuccessAt": data.get("lastSuccessAt") or "",
        "nextAllowedAt": next_allowed,
        "remainingMinutes": remaining,
        "delaySeconds": data.get("delaySeconds"),
    }


def fmkorea_recent_signals(limit: int = 12):
    if not FMKOREA_LOG.exists():
        return []
    patterns = (
        "FMKOREA_STATIC_LIST",
        "FMKOREA_BACKOFF_",
        "HERMES_FMKOREA_INGEST_",
        "UPSERT_OK",
        "WARN_FMKOREA_",
    )
    lines = []
    for line in FMKOREA_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        if any(pattern in line for pattern in patterns):
            lines.append(line)
    return lines[-limit:]


def fetch_production_feed():
    req = urllib.request.Request(
        PRODUCTION_FEED_URL,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "gajigaji-parser-status",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def production_source_summary(payload):
    grouped = {}
    for item in payload.get("items") or []:
        source = str(item.get("source") or "unknown")
        bucket = grouped.setdefault(source, {"items": 0, "latestUpdatedAt": "", "latestRegisteredAt": ""})
        bucket["items"] += 1
        updated_at = str(item.get("updatedAt") or "")
        registered_at = str(item.get("registeredAt") or "")
        if updated_at > bucket["latestUpdatedAt"]:
            bucket["latestUpdatedAt"] = updated_at
        if registered_at > bucket["latestRegisteredAt"]:
            bucket["latestRegisteredAt"] = registered_at
    return grouped


def health_label(summary):
    if not summary["exists"]:
        return "missing"
    if summary["items"] <= 0:
        return "empty"
    if summary["ageMinutes"] is None:
        return "unknown"
    if summary["ageMinutes"] > 180:
        return "stale"
    return "ok"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true", help="also fetch gaji.run production feed")
    args = parser.parse_args()

    sources = [source_summary(name, path) for name, path in ASSETS.items()]
    backoff = fmkorea_backoff_summary()

    print("Hotdeal parser status")
    for item in sources:
        age = "unknown" if item["ageMinutes"] is None else f"{item['ageMinutes']:.1f}m"
        print(
            f"- {item['source']}: {health_label(item)} "
            f"items={item['items']} age={age} staleFallback={item['staleFallback']}"
        )

    remaining = backoff["remainingMinutes"]
    remaining_text = "0.0m" if remaining is None else f"{remaining:.1f}m"
    print(
        "- fmkorea_backoff: "
        f"failures={backoff['failures']} remaining={remaining_text} "
        f"nextAllowedAt={backoff['nextAllowedAt'] or '-'} "
        f"lastSuccessAt={backoff['lastSuccessAt'] or '-'}"
    )

    print("Recent FMKorea signals:")
    for line in fmkorea_recent_signals():
        print(f"  {re.sub(r'\\s+', ' ', line).strip()}")

    if args.production:
        print("Production feed:")
        payload = fetch_production_feed()
        grouped = production_source_summary(payload)
        for source in sorted(grouped):
            item = grouped[source]
            updated_age = age_minutes(item["latestUpdatedAt"])
            updated_text = "unknown" if updated_age is None else f"{updated_age:.1f}m"
            print(
                f"- {source}: items={item['items']} "
                f"latestUpdatedAge={updated_text} "
                f"latestRegisteredAt={item['latestRegisteredAt'] or '-'}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
