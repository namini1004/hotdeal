# hotdeal-site handoff

Last updated: 2026-06-08 KST

## Current baseline

- Workspace: `C:\Users\namin\hotdeal-site`
- Repository: `https://github.com/namini1004/hotdeal.git`
- Branch: `main`
- Current baseline commit: `a970a9a` (`복구: 대화 중 UI 변경 재적용`)
- Production site: `https://gaji.run`
- Latest confirmed production deploy: `https://hotdeal-dp8ers0w4-namini1004-8834s-projects.vercel.app`
- Vercel production deploys are not assumed from git push alone. When the user asks for deploy, push to `main` first, then run a production Vercel deploy.

## Latest work summary, 2026-06-08

The UI work from the recent Codex conversation appeared to be rolled back because many changes had previously been deployed directly from the local working tree with `vercel deploy --prod`, but were not preserved in `main`. Later production deployments were created from the current `main`, so those direct-deploy-only changes disappeared from `gaji.run`.

Investigation findings:

- `main` and `origin/main` were aligned, but the expected UI changes were missing.
- Recent history contained revert commits: `87e4888` and `1c84434`.
- The previous good production deployment was `hotdeal-pz2hmy50u-namini1004-8834s-projects.vercel.app`.
- Current production at the time had a newer deployment, so the good deployment had been superseded.
- Representative missing markers included `settingsSortButton`, `gaji-board-btn`, the removed home top divider, dark-mode settings menu fixes, and detail favorite key reconciliation.

Recovery performed:

- Pulled the previous good deployment files back via `vercel curl`.
- Restored the conversation UI changes into the local working tree.
- Restored `.vercelignore` so local-only folders are ignored during Vercel deploy uploads.
- Committed the recovery as `a970a9a 복구: 대화 중 UI 변경 재적용`.
- Pushed `main` to `origin/main`.
- Ran `npx.cmd vercel deploy --prod`.
- Confirmed `https://gaji.run` aliases to the new production deployment.

Post-deploy checks:

- `https://gaji.run/index.html` contains `settingsSortButton`.
- `https://gaji.run/index.html` contains `gaji-board-btn`.
- The home action-bar divider remains removed (`border-bottom:1px solid var(--line)` is absent from the top bar rule).

## Product behavior to preserve

Home and settings:

- Home top tabs are hidden except the chips `전체`, `인기`, `최신`; `가지딜` remains hidden.
- The home top-right eggplant image button opens the board/가지가지 page.
- The home settings button opens a compact dropdown from the button, not a bottom sheet.
- The settings dropdown contains `정렬 방식`, `읽은글표시`, `다크모드`, and `설정`.
- `정렬 방식` opens a centered modal with latest/temperature options and an X close button.
- The sort icon changes between clock and thermometer according to the current sort mode.
- The dark-mode menu icon is sun when off and moon when on.
- Home action bar has no divider under it.
- List-view read highlighting spans edge-to-edge.
- List-view favorite hearts reflect detail favorite state.

Dark mode:

- Dark mode applies globally through `assets/theme.js`.
- Settings dropdown text is white in dark mode.
- Settings-page back buttons use a dark-mode background and visible text/icon color.
- Detail comment composer background is dark, with a visible light border.
- Detail `원본보기` stays readable in dark mode.
- List-view prices stay readable in dark mode.

Settings pages:

- `my-gaji.html` is the settings page with an Android-style action bar, `<` back button, and `설정` title.
- The settings page does not show read-highlight or dark-mode menu rows, because those live in the home settings dropdown.
- Settings subpages use compact white action bars in light mode and simple `<` back buttons aligned to the left.
- Nickname page title is `닉네임변경`, not `현재닉네임`.
- Nickname page uses the current profile image, not an `N` icon.

Create/detail/board:

- Hotdeal create price defaults to `0`; if empty, it is treated as `0원`, without extra explanatory text.
- Hotdeal create temperature defaults to `100` and has a `0-100` range slider.
- Markdown helper text is shortened to `마크다운 문법을 지원합니다.`.
- Board FAB sits low like the home FAB.
- Board page has a larger/left-shifted simple back button and no settings button.
- Board cards show author profile and nickname between title/tip/type/time content.
- Detail favorite state is reconciled across multiple keys so home grid/list hearts update consistently.
- Comment send button is a modern centered arrow inside a circular button.

## User preferences and cautions

- The user prefers Korean commit messages, usually starting with `요구사항:`, `수정:`, or clear Korean summaries.
- Do not report `assets/fmkorea_hotdeals_2days.json` as a normal dirty-file issue unless it is directly relevant.
- Do not touch `.codex-remote-attachments/`; it is local attachment data.
- Avoid production deploys unless the user explicitly asks for deployment.
- When deployment is requested: commit, push to `main`, then deploy production to `gaji.run`.
- Do not assume git push deploys production; `vercel.json` disables git deployment.

## Local checks

Useful quick checks:

```powershell
git status --short --branch
git log --oneline -10
npm.cmd test
```

`npm.cmd test` currently depends on local Python `pytest`. If `pytest` is not installed, the command fails before tests run.

Run the local server:

```powershell
npm.cmd run dev
```

Common local URL:

```text
http://127.0.0.1:3000/index.html
```

Note: `scripts/dev-server.mjs` currently listens on its internal default port; passing `-- --port 3001` did not move it during the recovery check.

## Deployment notes

Production deployment command used in this repo:

```powershell
npx.cmd vercel deploy --prod
```

After deploy, confirm the output URL and confirm that `https://gaji.run` is assigned to the latest production deployment.

Latest successful production deploy from this handoff:

```text
https://hotdeal-dp8ers0w4-namini1004-8834s-projects.vercel.app
```

Useful post-deploy marker checks:

```powershell
$html=(Invoke-WebRequest -Uri 'https://gaji.run/index.html' -UseBasicParsing -TimeoutSec 20).Content
$html -match 'settingsSortButton'
$html -match 'gaji-board-btn'
$html -match 'border-bottom:1px solid var\(--line\)'
```

Expected values after recovery: first two true, last false.

## Current dirty files after recovery

After the recovery commit and deploy, the working tree still had unrelated/local items:

- `assets/fmkorea_hotdeals_2days.json` modified
- `.codex-remote-attachments/` untracked

These were intentionally not included in the recovery commit.

## Next work checklist

- If UI appears rolled back again, first check whether a newer Vercel production deployment superseded the recovered deployment.
- Confirm `main` contains `a970a9a` or a later commit with the recovered UI markers.
- Before future deploys, commit and push intentional changes to `main`, then run `npx.cmd vercel deploy --prod`.
- Re-check dark mode on home, detail pages, create/edit pages, board pages, my page, and keyword pages after any theme changes.