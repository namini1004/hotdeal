import importlib.util
from datetime import datetime, timezone
from pathlib import Path


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
