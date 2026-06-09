# Cron job archive

이 폴더는 운영 중인 Hermes cron을 실행하기 위한 폴더가 아니라, 제거 전에 남겨둔 cron 정의 백업입니다.

## daily-gajigaji-shopping-tip-post

- 형태: Hermes LLM cron job
- Python 스크립트 기반 아님: `script`는 `null`, `no_agent`는 `false`
- 기존 스케줄: `0 12 * * *`
- 기능: gaji.run 가지가지 > 여러 가지 팁 글을 매일 1개 작성/게시

현재 이 파일은 저장용이며, 별도로 Hermes cron에 등록하지 않는 한 작동하지 않습니다.
