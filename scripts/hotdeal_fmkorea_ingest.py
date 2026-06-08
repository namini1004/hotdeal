#!/usr/bin/env python3
"""Cron-friendly entrypoint for FMKorea hotdeal local ingest.

This wrapper lets schedulers run the repo-owned FMKorea ingest script without
hardcoding a machine-specific checkout path. By default it resolves the repo
from this file's location; set HOTDEAL_REPO_DIR to run against another checkout.

It stays silent on success to avoid noisy cron notifications. On failure it
prints the last part of the child process output and exits non-zero.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 900


def resolve_repo() -> Path:
    override = os.environ.get("HOTDEAL_REPO_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def main() -> int:
    repo = resolve_repo()
    script = repo / "scripts" / "hermes_fmkorea_ingest.py"
    timeout = int(os.environ.get("HOTDEAL_FMKOREA_INGEST_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))

    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if proc.returncode != 0:
        print((proc.stdout or "")[-4000:])
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
