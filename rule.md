# Project Rules

## Git workflow

- If this project is connected to a Git repository, every completed change must be committed.
- If the repository has a configured remote, every completed commit must also be pushed.
- Commit messages must describe the user's request that caused the change.
- When multiple user-requested changes are completed together, include the relevant request descriptions in the commit message.
- Do not commit secrets, credentials, local environment files, or unrelated private machine state.
- If a repository has no configured remote, commit locally and clearly report that push was not possible.

## Deployment workflow

- Keep pushing code changes to Git as usual after completed work.
- Do **not** run Vercel production deployment by default.
- Run Vercel production deployment **only when the user explicitly requests it** (e.g., "배포해줘", "prod 배포해줘").
- Default verification flow after web changes: run local test server first, verify the updated page locally, and share a first-view screenshot with the user before any production deployment.
