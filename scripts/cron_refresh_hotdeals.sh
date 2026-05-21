#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/namin/hotdeal-site

# 1) 4개 피드 갱신 (각 소스 최대 3회 재시도)
run_with_retry() {
  local name="$1"
  local cmd="$2"
  local log_file="$3"
  local max=3
  local i
  for i in $(seq 1 "$max"); do
    if eval "$cmd" >"$log_file" 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

failed=0
run_with_retry "ppomppu" "python3 scripts/update_ppomppu_feed.py" "/tmp/hotdeal_ppomppu.log" || failed=$((failed+1))
run_with_retry "quasar"  "python3 scripts/update_quasar_feed.py"  "/tmp/hotdeal_quasar.log"  || failed=$((failed+1))
run_with_retry "fmkorea" "python3 scripts/update_fmkorea_feed.py" "/tmp/hotdeal_fmkorea.log" || failed=$((failed+1))
run_with_retry "ruliweb" "python3 scripts/update_ruliweb_feed.py" "/tmp/hotdeal_ruliweb.log" || failed=$((failed+1))

# 전부 실패하면 배포하지 않음
if [[ "$failed" -ge 4 ]]; then
  echo "all feed updates failed"
  exit 1
fi

# 2) 변경 감지(존재하는 경로만 추적)
TRACK_PATHS=(
  assets/ppomppu_hotdeals_2days.json
  assets/quasar_hotdeals_2days.json
  assets/fmkorea_hotdeals_2days.json
  assets/ruliweb_hotdeals_1day.json
)

for d in assets/ppomppu_thumbs assets/fmkorea_thumbs assets/ruliweb_thumbs; do
  [[ -e "$d" ]] && TRACK_PATHS+=("$d")
done

if git diff --quiet -- "${TRACK_PATHS[@]}"; then
  exit 0
fi

# 3) 단일 커밋 + 단일 배포(push)
git add "${TRACK_PATHS[@]}"

git commit -m "chore: 15m refresh hotdeals feeds (ppomppu/quasar/fmkorea/ruliweb)" >/dev/null
TOKEN=$(tr -d '\r\n' < /mnt/c/codex/pat.txt)
git push "https://x-access-token:${TOKEN}@github.com/namini1004/hotdeal.git" main >/dev/null

echo "updated and pushed"