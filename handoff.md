# hotdeal-site handoff

Last updated: 2026-06-08 KST

## Current baseline

- Workspace: `C:\Users\namin\hotdeal-site`
- Repository: `https://github.com/namini1004/hotdeal.git`
- Branch: `main`
- Current baseline commit: `9552580`
- Production site: `https://gaji.run`
- Vercel production deploys are not assumed from git push alone. When the user asks for deploy, push to `main` first, then run a production Vercel deploy.

## What was done in this handoff

The local working tree had uncommitted changes after commit `9552580`. Those local changes made the app look like older UI work had returned. They were reverted, so the codebase is back to the `9552580` baseline.

This file is the only intentional new repository change after that baseline.

## Latest functional baseline, commit 9552580

Commit `9552580` is the latest functional work to preserve.

It contains:

- Removed the profile button from the home top bar.
- Added a home settings button.
- Added a settings popup with profile, keyword alert, dark mode, and moved account/menu actions.
- Added global dark/white mode support through `assets/theme.js`.
- Linked the theme script across shared pages.
- Added user preference UI tests.

Recent important commits:

```text
9552580 home settings popup and global dark mode
27601e8 detail report controls and temperature edit improvements
3b8ee84 detail instant render order fix
b183937 detail entry cache rendering optimization
0de22e4 latest FMKorea auto-collection data reflected
4f06ce3 sort filter applies across home tabs
```

## User preferences and cautions

- The user prefers Korean commit messages, usually starting with `요구사항:` or `수정:`.
- Do not report the automatic collection JSON as a normal dirty-file issue unless it is directly relevant.
- Do not touch `.codex-remote-attachments/`; it is local attachment data.
- Avoid production deploys unless the user explicitly asks for deployment.
- When deployment is requested: commit, push to `main`, then deploy production to `gaji.run`.

## Product behavior to preserve

- Home settings popup should expose profile, keyword alerts, dark mode, and moved account/menu actions.
- Dark mode should apply globally via `assets/theme.js`.
- Detail view should show list-cached data immediately when available, then load remaining detail content naturally.
- Admin-only edit/delete controls should be hidden from normal users.
- Normal users should see report behavior.
- App-facing text should use "가지", not "가지딜".
- Hotdeal create/edit temperature supports `0-100`, defaulting to `100`.
- Detail home icon belongs near the left back button, not on the far right.

## Local checks

Useful quick checks:

```powershell
git status --short --branch
git log --oneline -10
python -m pytest
```

Run the local server:

```powershell
npm run dev
```

Common local URL:

```text
http://127.0.0.1:4173/index.html
```

## Deployment notes

Production deployment command used in this repo:

```powershell
npx.cmd vercel deploy --prod
```

After deploy, confirm the output URL and confirm that `https://gaji.run` is assigned to the latest production deployment.

## Next work checklist

- Re-check the home settings popup on mobile and desktop after deployment.
- Verify dark mode on `index.html`, detail pages, create/edit pages, board pages, my page, and keyword pages.
- On another machine, start with `git pull origin main`, then read this file.
