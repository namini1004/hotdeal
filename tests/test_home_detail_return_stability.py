from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_index():
    return (ROOT / "index.html").read_text(encoding="utf-8")


def test_failed_list_images_are_reused_as_fallback_without_retrying():
    html = read_index()

    assert "const FAILED_IMAGE_URLS_KEY = 'hotdeal_failed_image_urls_v1';" in html
    assert "function rememberFailedImageUrl(url)" in html
    assert "sessionStorage.setItem(FAILED_IMAGE_URLS_KEY, JSON.stringify(recent))" in html
    assert "function resolveListImageUrl(src)" in html
    assert "getFailedImageUrls().has(optimized) ? FALLBACK_IMAGE : optimized" in html
    assert 'src="${resolveListImageUrl(item.img)}"' in html
    assert 'onerror="useFallbackListImage(this)"' in html


def test_pageshow_preserves_existing_list_dom_and_only_syncs_read_state():
    html = read_index()
    handler = html.split("window.addEventListener('pageshow', () => {", 1)[1].split("});", 1)[0]

    assert "if(syncSearchStateFromInput()) render();" in handler
    assert "else syncReadHighlightClasses();" in handler
    assert "restoreListScrollState();" in handler
    assert "syncSearchStateFromInput();\n        render();" not in handler


def test_detail_return_skips_immediate_feed_refresh_and_keeps_cached_order():
    html = read_index()

    assert "detailReturnRefreshBlockedUntil = Date.now() + DETAIL_RETURN_REFRESH_BLOCK_MS;" in html
    visibility = html.split("function bindAutoSync(){", 1)[1].split("function bindPwaInstallPrompt(){", 1)[0]
    assert visibility.index("if(Date.now() < detailReturnRefreshBlockedUntil) return;") < visibility.index("refreshFeed({ silent: true });")
    assert "const preserveReturnedList = !state.initialFeedLoading && Date.now() < detailReturnRefreshBlockedUntil;" in html
    assert "}else if(preserveReturnedList || !needsFreshTemperature){" in html
    assert "if(!preserveReturnedList){\n        await refreshFeed" in html
