import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[1]


def load_sync_module():
    spec = importlib.util.spec_from_file_location(
        "sync_hotdeals_temperature_snapshots",
        ROOT / "scripts" / "sync_hotdeals_to_supabase.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_temperature_snapshot_aggregates_each_source_into_one_30_minute_row():
    sync = load_sync_module()
    captured_at = datetime(2026, 8, 27, 9, 47, tzinfo=timezone.utc)
    rows = [
        {
            "source": "ppomppu",
            "registered_at": "2026-08-27T08:47:00+00:00",
            "views": 100,
            "comments": 0,
            "likes": 0,
            "dislikes": 0,
            "comment_signal_score": 0,
        },
        {
            "source": "ppomppu",
            "registered_at": "2026-08-27T07:47:00+00:00",
            "views": 300,
            "comments": 4,
            "likes": 0,
            "dislikes": 1,
            "comment_signal_score": -8,
        },
        {
            "source": "fmkorea",
            "registered_at": "2026-08-27T09:17:00+00:00",
            "views": 0,
            "comments": 0,
            "likes": 10,
            "dislikes": 0,
            "comment_signal_score": 2,
        },
    ]

    snapshots = sync.build_temperature_snapshot_rows(rows, captured_at)
    by_source = {row["source"]: row for row in snapshots}

    assert set(by_source) == {"ppomppu", "fmkorea"}
    assert by_source["ppomppu"]["captured_at"] == "2026-08-27T09:30:00+00:00"
    assert by_source["ppomppu"]["sample_count"] == 2
    assert by_source["ppomppu"]["metrics"]["views"]["mean"] == 200
    assert by_source["ppomppu"]["metrics"]["views"]["variance"] == 10000
    assert by_source["ppomppu"]["metrics"]["views"]["p50"] == 200
    assert by_source["ppomppu"]["metrics"]["comments"]["nonZeroRate"] == 0.5
    assert by_source["ppomppu"]["metrics"]["age_hours"]["mean"] == 1.5
    assert by_source["fmkorea"]["metrics"]["likes"]["max"] == 10


def test_temperature_snapshot_ignores_non_feed_sources():
    sync = load_sync_module()
    snapshots = sync.build_temperature_snapshot_rows(
        [{"source": "user", "registered_at": "2026-08-27T09:00:00Z", "views": 999}],
        datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
    )
    assert snapshots == []


def test_partial_feed_is_delete_protected_but_not_a_stale_observation(tmp_path, monkeypatch):
    sync = load_sync_module()
    feed = tmp_path / "quasar.json"
    monkeypatch.setattr(sync, "FEED_FILES", [feed])
    for stale in (False, True):
        feed.write_text(json.dumps({"sourceKey": "quasar", "partialSnapshot": True,
                                    "staleFallback": stale, "items": [{"source": "quasar"}]}), encoding="utf-8")
        _, protected, stale_sources = sync.load_feed_data()
        assert protected == {"quasar"}
        assert stale_sources == ({"quasar"} if stale else set())


def test_partial_snapshot_uses_active_48_hour_population_after_writes():
    sync = load_sync_module()
    now = datetime(2026, 9, 27, 3, tzinfo=timezone.utc)

    def row(post_id, **extra):
        return {"id": post_id, "source": "quasar", "source_post_id": post_id,
                "source_link": f"https://quasarzone.com/bbs/qb_saleinfo/views/{post_id}",
                "registered_at": "2026-09-27T01:00:00Z", "views": 100, **extra}

    existing = [row("1"), row("2"), row("3", deleted_at="2026-09-27T01:00:00Z"),
                row("4", registered_at="2026-09-01T00:00:00Z"),
                row("5", registered_at="2026-09-29T00:00:00Z"), row("6"),
                row("7", source="ruliweb"), row("8", registered_at=None)]
    changed = [row("1", views=900), row("9", views=500)]
    rows = sync.build_temperature_snapshot_input(changed, existing, changed, [{"id": "6"}], now)
    assert {item["id"] for item in rows} == {"1", "2", "9"}
    snapshot = sync.build_temperature_snapshot_rows(rows, now)[0]
    assert snapshot["sample_count"] == 3
    assert snapshot["metrics"]["views"]["mean"] == 500
    assert sync.build_temperature_snapshot_input([], existing, [], [], now) == []


def test_genuinely_stale_fallback_still_cannot_write_snapshots(monkeypatch):
    sync = load_sync_module()
    post = MagicMock()
    monkeypatch.setattr(sync.requests, "post", post)
    written = sync.record_temperature_snapshots(
        [{"source": "quasar", "registered_at": "2026-09-27T01:00:00Z"}],
        "https://example.test", "test", datetime(2026, 9, 27, 3, tzinfo=timezone.utc),
        skip_sources={"quasar"},
    )
    assert written == 0
    post.assert_not_called()
