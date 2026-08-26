#!/usr/bin/env python3
"""Refresh and sync only Ppomppu deals from the local network."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = Path(os.environ.get("HOTDEAL_PPOMPPU_ARTIFACT_DIR", ROOT / ".artifacts" / "ppomppu-ingest"))
FEED_PATH = Path(os.environ.get("HOTDEAL_PPOMPPU_JSON_PATH", ARTIFACT_DIR / "ppomppu_hotdeals_2days.json"))
LOG_PATH = Path(
    os.environ.get(
        "HOTDEAL_PPOMPPU_INGEST_LOG",
        ROOT / ".artifacts" / "logs" / "hotdeal_ppomppu_ingest.log",
    )
)
LOCK_PATH = Path(os.environ.get("HOTDEAL_PPOMPPU_LOCK_PATH", ARTIFACT_DIR / "ingest.lock"))
LOCK_STALE_SECONDS = int(os.environ.get("HOTDEAL_PPOMPPU_LOCK_STALE_SECONDS", "900"))


def append_log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message.rstrip()}\n")


def parse_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if key and not os.environ.get(key):
            os.environ[key] = value


def load_secret_file(env_name: str, env_path_name: str, default_path: Path) -> None:
    if os.environ.get(env_name):
        return
    path = Path(os.environ.get(env_path_name, default_path))
    if path.exists():
        os.environ[env_name] = path.read_text(encoding="utf-8").strip()


def load_environment() -> None:
    explicit = os.environ.get("HOTDEAL_ENV_FILE", "").strip()
    if explicit:
        parse_env_file(Path(explicit))
    parse_env_file(ROOT / ".env.local")
    parse_env_file(ROOT / ".env")

    load_secret_file("SUPABASE_URL", "HOTDEAL_SUPABASE_URL_FILE", ROOT / "supabase_url.txt")
    load_secret_file(
        "SUPABASE_SERVICE_ROLE_KEY",
        "HOTDEAL_SUPABASE_SERVICE_ROLE_KEY_FILE",
        ROOT / "supabase_service_role_key.txt",
    )
    load_secret_file(
        "PUSH_INGEST_SECRET",
        "HOTDEAL_PUSH_INGEST_SECRET_FILE",
        ROOT / "push_ingest_secret.txt",
    )
    os.environ.setdefault("PUSH_INGEST_URL", "https://gaji.run/api/push/ingest")


@contextmanager
def ingest_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        age = datetime.now().timestamp() - LOCK_PATH.stat().st_mtime
        if age >= LOCK_STALE_SECONDS:
            LOCK_PATH.unlink(missing_ok=True)
        else:
            append_log(f"PPOMPPU_LOCAL_SKIP reason=already_running lock_age_seconds={int(age)}")
            yield False
            return

    try:
        descriptor = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        append_log("PPOMPPU_LOCAL_SKIP reason=lock_race")
        yield False
        return

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\nstarted_at={datetime.now(timezone.utc).isoformat()}\n")
        yield True
    finally:
        LOCK_PATH.unlink(missing_ok=True)


def run_step(args: list[str], env: dict[str, str], timeout: int) -> str:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    output = proc.stdout or ""
    append_log(f"$ {' '.join(args)}\n{output.strip()}\nexit={proc.returncode}")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{output[-4000:]}")
    return output


def validate_feed(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("Ppomppu parser returned no items; existing database rows were left untouched")
    invalid_sources = [item for item in items if str(item.get("source") or "").strip() != "ppomppu"]
    if invalid_sources:
        raise RuntimeError(f"Ppomppu feed contains {len(invalid_sources)} rows from another source")
    return len(items)


def main() -> int:
    load_environment()
    missing = [name for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY") if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"missing required environment: {', '.join(missing)}")

    with ingest_lock() as acquired:
        if not acquired:
            return 0

        env = os.environ.copy()
        env["HOTDEAL_PPOMPPU_JSON_PATH"] = str(FEED_PATH)
        env.setdefault("HOTDEAL_PPOMPPU_MAX_PAGES", "1")
        env.setdefault("HOTDEAL_PPOMPPU_MAX_NEW_DETAILS", "15")
        env["HOTDEAL_PPOMPPU_PARTIAL_SNAPSHOT"] = "1"
        env["HOTDEAL_FEED_FILES"] = str(FEED_PATH)
        env["HOTDEAL_EXPECTED_FEED_SOURCES"] = "ppomppu"
        env.setdefault("PUSH_INGEST_BATCH_SIZE", "10")
        env.setdefault("PUSH_INGEST_MAX_ROWS", "50")

        append_log(
            "PPOMPPU_LOCAL_START "
            f"feed={FEED_PATH} max_pages={env['HOTDEAL_PPOMPPU_MAX_PAGES']} "
            f"max_new_details={env['HOTDEAL_PPOMPPU_MAX_NEW_DETAILS']} "
            f"push={'enabled' if env.get('PUSH_INGEST_SECRET') else 'disabled'}"
        )
        parser_output = run_step(
            [sys.executable, "scripts/update_ppomppu_feed.py"],
            env,
            timeout=int(os.environ.get("HOTDEAL_PPOMPPU_PARSE_TIMEOUT", "240")),
        )
        item_count = validate_feed(FEED_PATH)
        sync_output = run_step(
            [sys.executable, "scripts/sync_hotdeals_to_supabase.py"],
            env,
            timeout=int(os.environ.get("HOTDEAL_PPOMPPU_SYNC_TIMEOUT", "600")),
        )
        summary_lines = [
            line
            for line in (parser_output + "\n" + sync_output).splitlines()
            if line.strip() and not line.startswith("WARN_IMAGE_MIRROR_SKIP")
        ]
        append_log(f"PPOMPPU_LOCAL_DONE items={item_count}\n" + "\n".join(summary_lines[-30:]))
        print(f"PPOMPPU_LOCAL_DONE items={item_count}")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        append_log(f"PPOMPPU_LOCAL_ERROR {exc}")
        print(f"PPOMPPU_LOCAL_ERROR {exc}", file=sys.stderr)
        raise
