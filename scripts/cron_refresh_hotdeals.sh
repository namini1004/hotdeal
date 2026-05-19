#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/namin/hotdeal-site

# 1) 피드 갱신
OUT=$(python3 scripts/update_ppomppu_feed.py)

# 변경 없으면 조용히 종료 (no_agent=True에서 silent)
if [[ "$OUT" == "NO_CHANGE"* ]]; then
  exit 0
fi

# 2) 변경 커밋/푸시
if ! git diff --quiet -- assets/ppomppu_hotdeals_2days.json assets/ppomppu_thumbs; then
  git add assets/ppomppu_hotdeals_2days.json assets/ppomppu_thumbs
  git commit -m "chore: hourly refresh ppomppu hotdeals feed" >/dev/null
  TOKEN=$(tr -d '\r\n' < /mnt/c/codex/pat.txt)
  git push "https://x-access-token:${TOKEN}@github.com/namini1004/hotdeal.git" main >/dev/null
  echo "$OUT | pushed"
fi
