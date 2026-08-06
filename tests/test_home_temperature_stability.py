from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_detail_fetch_never_rewrites_the_home_feed_cache():
    detail = read("indexdetail.html")
    latest_block = detail.split("const latest = await fetchItemById(id);", 1)[1].split("}catch(error){", 1)[0]

    assert "saveCachedDetail(latest);" in latest_block
    assert "saveItems(" not in latest_block
    assert "existingIdx" not in latest_block
    assert "next.push(latest)" not in latest_block
    assert "function saveItems(items)" not in detail


def test_background_refresh_keeps_existing_temperatures():
    home = read("index.html")

    assert "function preserveExistingTemperatures(items, existingItems = state.feedItems)" in home
    assert "temperature: existing.temperature" in home
    assert "hotScore: existing.hotScore" in home
    assert "const acceptsRecalculatedTemperature = mode === 'entry' || mode === 'manual';" in home
    assert ": preserveExistingTemperatures(normalizedIncoming);" in home


def test_incomplete_legacy_temperature_cache_is_recalculated_on_entry():
    home = read("index.html")

    assert "!needsFreshTemperature && Date.now() < detailReturnRefreshBlockedUntil" in home
    assert "if(!preserveReturnedList && !needsFreshTemperature) render();" in home
    assert "mode: needsFreshTemperature ? 'manual' : 'entry'" in home
