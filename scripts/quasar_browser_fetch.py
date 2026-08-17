#!/usr/bin/env python3
"""Persistent-Chrome fetcher for the local Quasar collector."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit


class QuasarBrowserFetchError(RuntimeError):
    def __init__(self, message: str, *, blocked: bool = False):
        super().__init__(message)
        self.blocked = blocked


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _same_image_url(left: str, right: str) -> bool:
    try:
        a = urlsplit(str(left or ""))
        b = urlsplit(str(right or ""))
        return bool(a.netloc and b.netloc and a.netloc.lower() == b.netloc.lower() and a.path == b.path)
    except Exception:
        return False


class QuasarBrowserFetcher:
    """Drive installed Chrome via Playwright's Chromium debugging protocol."""

    def __init__(self, profile_dir: str | Path | None = None):
        root = Path(__file__).resolve().parents[1]
        self.profile_dir = Path(
            profile_dir
            or os.environ.get(
                "HOTDEAL_QUASAR_BROWSER_PROFILE_DIR",
                root / ".artifacts" / "quasar-browser-profile",
            )
        )
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = None
        self._context = None
        self._page = None

    def start(self):
        if self._context:
            return self
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise QuasarBrowserFetchError("playwright is not installed") from exc

        self._playwright = sync_playwright().start()
        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                channel=os.environ.get("HOTDEAL_QUASAR_BROWSER_CHANNEL", "chrome"),
                headless=_env_flag("HOTDEAL_QUASAR_BROWSER_HEADLESS", True),
                viewport={"width": 1280, "height": 1200},
                locale="ko-KR",
                args=["--disable-background-networking", "--no-first-run", "--no-default-browser-check"],
            )
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            self._page.set_default_navigation_timeout(45_000)
            self._page.set_default_timeout(15_000)
            return self
        except Exception:
            self.close()
            raise

    def get_html(self, url: str, timeout_seconds: int = 45) -> str:
        self.start()
        response = self._page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=max(1, int(timeout_seconds)) * 1000,
        )
        status = response.status if response else 0
        if status in {403, 429, 430}:
            raise QuasarBrowserFetchError(f"browser navigation blocked ({status})", blocked=True)
        if status >= 500:
            raise QuasarBrowserFetchError(f"browser navigation failed ({status})")
        self._page.wait_for_timeout(700)
        html = self._page.content()
        if len(html) < 500:
            raise QuasarBrowserFetchError("browser returned an unexpectedly small page")
        return html

    def capture_image(self, source_link: str, image_url: str) -> bytes:
        self.get_html(source_link, timeout_seconds=45)
        images = self._page.locator("img")
        count = min(images.count(), 250)
        for index in range(count):
            locator = images.nth(index)
            try:
                candidates = locator.evaluate(
                    "el => [el.currentSrc, el.src, el.dataset?.src, el.dataset?.original].filter(Boolean)"
                )
                if not any(_same_image_url(value, image_url) for value in candidates or []):
                    continue
                locator.scroll_into_view_if_needed()
                self._page.wait_for_timeout(500)
                body = locator.screenshot(type="png")
                if len(body) >= 500:
                    return body
            except Exception:
                continue

        response = self._page.goto(image_url, wait_until="load", timeout=45_000)
        status = response.status if response else 0
        if status in {403, 429, 430}:
            raise QuasarBrowserFetchError(f"browser image navigation blocked ({status})", blocked=True)
        if status >= 500:
            raise QuasarBrowserFetchError(f"browser image navigation failed ({status})")
        image = self._page.locator("img").first
        image.wait_for(state="visible", timeout=10_000)
        body = image.screenshot(type="png")
        if len(body) < 500:
            raise QuasarBrowserFetchError("browser image screenshot is too small")
        return body

    def close(self):
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        self._context = None
        self._page = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._playwright = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, traceback):
        self.close()
