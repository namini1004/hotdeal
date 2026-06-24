#!/usr/bin/env python3
"""Run FMKorea-only feed refresh and Supabase upsert from local/Hermes cron.

GitHub-hosted runners can be blocked by FMKorea's security system, so this
script intentionally runs the FMKorea parser locally and syncs only FMKorea rows.
It is safe for no-agent Hermes cron: stdout is silent by default, while errors
still surface via the scheduler.
"""
import argparse
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = Path(os.environ.get("HOTDEAL_HERMES_FMKOREA_LOG", "/home/namin/.hermes/logs/hotdeal_fmkorea_ingest.log"))
DEFAULT_ENV_FILES = [
    ROOT / ".env.local",
    ROOT / ".env",
    Path("/home/namin/.hermes/hotdeal.env"),
]


def append_log(message: str):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {message.rstrip()}\n")


def parse_env_file(path: Path):
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
        if not os.environ.get(key):
            os.environ[key] = value


def load_environment():
    explicit = os.environ.get("HOTDEAL_ENV_FILE", "").strip()
    if explicit:
        parse_env_file(Path(explicit))
    for path in DEFAULT_ENV_FILES:
        parse_env_file(path)

    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        return

    url_path = Path(os.environ.get("HOTDEAL_SUPABASE_URL_FILE", "/mnt/c/codex/supabase_url.txt"))
    key_paths = [Path(os.environ.get("HOTDEAL_SUPABASE_SERVICE_ROLE_KEY_FILE", "/mnt/c/codex/supabase_service_role_key.txt"))]
    # Accept the typo filename too, because the credential file may be created
    # manually from Windows Explorer or a messenger instruction.
    key_paths.append(Path("/mnt/c/codex/supabase_service_role_ley.txt"))
    if not os.environ.get("SUPABASE_URL") and url_path.exists():
        os.environ["SUPABASE_URL"] = url_path.read_text(encoding="utf-8").strip()
    if not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        for key_path in key_paths:
            if key_path.exists():
                os.environ["SUPABASE_SERVICE_ROLE_KEY"] = key_path.read_text(encoding="utf-8").strip()
                break

    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        return

    # Pull production env from Vercel as a local-only fallback. The temp file is
    # deleted after loading; secret values are never printed.
    tmp_path = Path(tempfile.gettempdir()) / f"hotdeal-vercel-env-{os.getpid()}.local"
    try:
        tmp_path.unlink(missing_ok=True)
        subprocess.run(
            ["vercel", "env", "pull", str(tmp_path), "--environment=production", "--yes"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        parse_env_file(tmp_path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def run_step(args, *, env=None, timeout=600):
    proc = subprocess.run(
        args,
        cwd=ROOT,
        env=env or os.environ.copy(),
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="print parser/sync summary to stdout")
    args = parser.parse_args()

    load_environment()
    missing = [key for key in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY") if not os.environ.get(key)]
    if missing:
        raise RuntimeError(f"missing required environment: {', '.join(missing)}")

    env = os.environ.copy()
    env.setdefault("FMKOREA_DIAGNOSTIC_DIR", str(ROOT / ".artifacts" / "hermes-fmkorea-diagnostics"))
    env["HOTDEAL_FEED_FILES"] = str(ROOT / "assets" / "fmkorea_hotdeals_2days.json")
    env["HOTDEAL_EXPECTED_FEED_SOURCES"] = "fmkorea"

    parser_output = run_step([sys.executable, "scripts/update_fmkorea_feed.py"], env=env, timeout=540)
    if (
        "FMKOREA_BACKOFF_SKIP" in parser_output
        or "FMKOREA_BACKOFF_SET" in parser_output
        or "FMKOREA_BACKOFF_READONLY_SECURITY" in parser_output
    ):
        append_log(f"HERMES_FMKOREA_INGEST_SKIPPED\n{parser_output.strip()[-4000:]}")
        if args.verbose:
            print(parser_output.strip()[-4000:])
        return

    sync_output = run_step([sys.executable, "scripts/sync_hotdeals_to_supabase.py"], env=env, timeout=300)

    summary = "\n".join(line for line in (parser_output + sync_output).splitlines() if line.strip())[-4000:]
    append_log(f"HERMES_FMKOREA_INGEST_DONE\n{summary}")
    if args.verbose:
        print(summary)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        append_log(f"HERMES_FMKOREA_INGEST_ERROR {exc}")
        print(f"HERMES_FMKOREA_INGEST_ERROR {exc}", file=sys.stderr)
        raise
