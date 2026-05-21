#!/usr/bin/env bash
set -euo pipefail
cd /mnt/c/Users/namin/hotdeal-site

# 1) 4개 피드 갱신
python3 scripts/update_ppomppu_feed.py >/tmp/hotdeal_ppomppu.log 2>&1
python3 scripts/update_quasar_feed.py  >/tmp/hotdeal_quasar.log 2>&1
python3 scripts/update_fmkorea_feed.py >/tmp/hotdeal_fmkorea.log 2>&1
python3 scripts/update_ruliweb_feed.py >/tmp/hotdeal_ruliweb.log 2>&1

# 2) 변경 감지(피드 JSON/썸네일)
if git diff --quiet -- \
  assets/ppomppu_hotdeals_2days.json \
  assets/quasar_hotdeals_2days.json \
  assets/fmkorea_hotdeals_2days.json \
  assets/ruliweb_hotdeals_1day.json \
  assets/ppomppu_thumbs \
  assets/fmkorea_thumbs \
  assets/ruliweb_thumbs; then
  exit 0
fi

# 3) 단일 커밋 + 단일 배포(push)
git add \
  assets/ppomppu_hotdeals_2days.json \
  assets/quasar_hotdeals_2days.json \
  assets/fmkorea_hotdeals_2days.json \
  assets/ruliweb_hotdeals_1day.json \
  assets/ppomppu_thumbs \
  assets/fmkorea_thumbs \
  assets/ruliweb_thumbs

git commit -m "chore: 15m refresh hotdeals feeds (ppomppu/quasar/fmkorea/ruliweb)" >/dev/null
TOKEN=$(tr -d '\r\n' < /mnt/c/codex/pat.txt)
git push "https://x-access-token:${TOKEN}@github.com/namini1004/hotdeal.git" main >/dev/null

echo "updated and pushed"