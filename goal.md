# Goal: Gaji Service Architecture

## Final structure

`hotdeal-site` is the main product.

- Runs as the public web service.
- Provides the shared UI for mobile web, desktop web, Android WebView, and future iOS WebView.
- Owns content screens: home, hotdeal list, board list, detail, create, edit, delete, share, and My Gaji.
- Owns web login screens and account state.
- Evolves into a PWA so users can install it from mobile and desktop browsers.

`hotdeal-android` is a thin native app shell.

- Loads `hotdeal-site` in WebView.
- Owns Android-only capabilities: native bottom tabs, push token management, Android share target, file chooser permissions, app store packaging, and notification deep links.
- Does not duplicate content UI that already exists in the web app.

Future iOS app should follow the same pattern.

- WKWebView loads the same `hotdeal-site`.
- iOS-only code handles push, share extension, permissions, and store packaging.

## Ownership rules

- Content UI lives in `hotdeal-site`.
- Create/edit/detail/share/delete flows live in `hotdeal-site`.
- Login is web-first so Android, iOS, mobile web, and desktop web use the same account system.
- Native apps only bridge platform capabilities into the web service.
- Data and account state must be owned by a shared backend, not by a single native app.

## PWA direction

`hotdeal-site` should become a PWA.

- Add `manifest.webmanifest`.
- Add app icons and theme color.
- Add service worker for safe static-asset caching.
- Keep all key screens responsive for mobile and desktop.
- Use web push later if it fits the notification plan.

PWA is still a website, but it adds installability, app-like launch behavior, icons, theme color, and optional offline/cache behavior. Native Android/iOS apps remain useful for push reliability, share targets, app store presence, and platform permissions.

## Phase 1: Web foundation

- Keep `hotdeal-site` as the source of truth for screens and content flows.
- Make My Gaji load as the fourth tab destination.
- Add web-first Google login first.
- Add account status API and logout API.
- Document which provider keys must be configured by the owner.
- Do not put provider secrets in source code.

## Phase 2: Account-backed features

- Add a `profiles` table or equivalent account store.
- Associate user-created deals and board posts with the logged-in user.
- Show My Gaji content: my posts, saved deals, notification preferences, and account settings.
- Add edit/delete permissions based on ownership.

## Phase 3: PWA

- Add manifest, service worker, icons, and install-friendly metadata.
- Verify mobile Safari, Android Chrome, and desktop Chrome behavior.
- Decide whether to support web push directly or only native app push first.

## Phase 4: Native app bridges

- Android loads the existing web screens.
- Android manages four native tabs: Home, GajiGaji, Chat, My Gaji.
- Android forwards shared URLs into the web create flow.
- Android registers push tokens after web login is confirmed.
- Android opens notification deep links into the matching web route.

## Owner setup needed for social login

Google login needs:

- Google Cloud OAuth client for a web application.
- Authorized redirect URI: `https://hotdeal-omega.vercel.app/api/auth`
- Vercel environment variables:
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`

Shared auth needs:

- Vercel environment variable:
  - `AUTH_SESSION_SECRET`
- Use a long random value. Do not commit it.
