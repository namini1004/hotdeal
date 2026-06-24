import json

from scripts import update_fmkorea_feed as fmkorea
from scripts import update_ppomppu_feed as ppomppu
from scripts import update_quasar_feed as quasar


def test_fmkorea_uses_latest_listing_not_popular_sort():
    assert "sort_index=pop" not in fmkorea.LIST_URL
    assert "mid=hotdeal" in fmkorea.LIST_URL


def test_fmkorea_filters_old_rows_before_detail_parse():
    now = fmkorea.datetime(2026, 6, 3, 12, 0, tzinfo=fmkorea.KST)
    since = now - fmkorea.timedelta(hours=48)
    row = {"lines": ["먹거리 / 2026.05.31 / tester / 추천 1"], "raw": ""}

    assert fmkorea.should_keep_row_by_time(row, now, since) is False
    assert row["_meta"]["time_token"] == "2026.05.31"


def test_fmkorea_keeps_recent_rows_before_detail_parse():
    now = fmkorea.datetime(2026, 6, 3, 12, 0, tzinfo=fmkorea.KST)
    since = now - fmkorea.timedelta(hours=48)
    row = {"lines": ["가전제품 / 11:37 / wakfu / 추천 14"], "raw": ""}

    assert fmkorea.should_keep_row_by_time(row, now, since) is True
    assert row["_meta"]["category"] == "가전제품"


def test_fmkorea_reuses_cached_detail_fields_by_document_id():
    cached = {
        "id": "123456",
        "sourceLink": "https://m.fmkorea.com/?mid=hotdeal&document_srl=123456",
        "img": "https://img.example/fmkorea.webp",
        "buyLink": "https://shop.example/item",
        "desc": "이미 파싱한 상세 본문",
    }
    lookup = fmkorea.build_previous_detail_lookup([cached])

    row = {
        "href": "https://m.fmkorea.com/index.php?mid=hotdeal&document_srl=123456&page=2",
        "img": "https://static.fmkorea.com/logos/mobile/fmkorea.png",
    }

    reused = fmkorea.apply_cached_detail_fields(row, lookup)

    assert reused is True
    assert row["img"] == cached["img"]
    assert row["buyLink"] == cached["buyLink"]
    assert row["desc"] == cached["desc"]


def test_fmkorea_does_not_skip_when_cached_detail_is_incomplete():
    lookup = fmkorea.build_previous_detail_lookup([
        {
            "id": "123456",
            "sourceLink": "https://m.fmkorea.com/?mid=hotdeal&document_srl=123456",
            "buyLink": "https://shop.example/item",
            "desc": "",
        }
    ])
    row = {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=123456"}

    assert fmkorea.apply_cached_detail_fields(row, lookup) is False
    assert "buyLink" not in row


def test_fmkorea_incremental_stops_after_page1_when_tail_is_known(monkeypatch):
    now = fmkorea.datetime(2026, 6, 3, 12, 0, tzinfo=fmkorea.KST)
    since = now - fmkorea.timedelta(hours=48)
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return [
            {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=101", "lines": [], "raw": ""},
            {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=100", "lines": [], "raw": ""},
        ], False

    monkeypatch.setattr(fmkorea, "fetch_static_page", fake_fetch)
    monkeypatch.setattr(fmkorea, "should_keep_row_by_time", lambda row, now, since: True)

    rows, security_blocked = fmkorea.collect_recent_rows(
        None,
        now,
        since,
        [{"id": "100", "sourceLink": "https://m.fmkorea.com/?mid=hotdeal&document_srl=100"}],
    )

    assert len(rows) == 2
    assert security_blocked is False
    assert len(calls) == 1
    assert "page=1" in calls[0]


def test_fmkorea_incremental_stops_when_any_tail_sample_is_known(monkeypatch):
    now = fmkorea.datetime(2026, 6, 3, 12, 0, tzinfo=fmkorea.KST)
    since = now - fmkorea.timedelta(hours=48)
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return [
            {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=103", "lines": [], "raw": ""},
            {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=102", "lines": [], "raw": ""},
            {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=101", "lines": [], "raw": ""},
            {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=100", "lines": [], "raw": ""},
        ], False

    monkeypatch.setattr(fmkorea, "fetch_static_page", fake_fetch)
    monkeypatch.setattr(fmkorea, "should_keep_row_by_time", lambda row, now, since: True)

    rows, security_blocked = fmkorea.collect_recent_rows(
        None,
        now,
        since,
        [{"id": "101", "sourceLink": "https://m.fmkorea.com/?mid=hotdeal&document_srl=101"}],
    )

    assert len(rows) == 4
    assert security_blocked is False
    assert len(calls) == 1
    assert "page=1" in calls[0]


def test_fmkorea_incremental_fetches_page2_when_page1_tail_is_new(monkeypatch):
    now = fmkorea.datetime(2026, 6, 3, 12, 0, tzinfo=fmkorea.KST)
    since = now - fmkorea.timedelta(hours=48)
    calls = []
    sleeps = []

    def fake_fetch(url):
        calls.append(url)
        if "page=1" in url:
            return [
                {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=102", "lines": [], "raw": ""},
                {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=101", "lines": [], "raw": ""},
            ], False
        return [
            {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=100", "lines": [], "raw": ""},
        ], False

    monkeypatch.setattr(fmkorea, "fetch_static_page", fake_fetch)
    monkeypatch.setattr(fmkorea, "should_keep_row_by_time", lambda row, now, since: True)
    monkeypatch.setattr(fmkorea.time, "sleep", lambda seconds: sleeps.append(seconds))

    rows, security_blocked = fmkorea.collect_recent_rows(
        None,
        now,
        since,
        [{"id": "100", "sourceLink": "https://m.fmkorea.com/?mid=hotdeal&document_srl=100"}],
    )

    assert len(rows) == 3
    assert security_blocked is False
    assert len(calls) == 2
    assert "page=1" in calls[0]
    assert "page=2" in calls[1]
    assert sleeps == [fmkorea.PAGE_DELAY_SECONDS]


def test_fmkorea_incremental_stops_immediately_on_security_response(monkeypatch):
    now = fmkorea.datetime(2026, 6, 3, 12, 0, tzinfo=fmkorea.KST)
    since = now - fmkorea.timedelta(hours=48)
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return [], True

    monkeypatch.setattr(fmkorea, "fetch_static_page", fake_fetch)

    rows, security_blocked = fmkorea.collect_recent_rows(None, now, since, [])

    assert rows == []
    assert security_blocked is True
    assert len(calls) == 1


def test_fmkorea_browser_fallback_recovers_static_security_response(monkeypatch):
    now = fmkorea.datetime(2026, 6, 3, 12, 0, tzinfo=fmkorea.KST)
    since = now - fmkorea.timedelta(hours=48)

    def fake_fetch(url):
        return [], True

    browser_rows = [
        {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=101", "lines": [], "raw": ""},
        {"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=100", "lines": [], "raw": ""},
    ]

    monkeypatch.setattr(fmkorea, "fetch_static_page", fake_fetch)
    monkeypatch.setattr(fmkorea, "browser_fallback_enabled", lambda: True)
    monkeypatch.setattr(fmkorea, "run_page_extract", lambda page, url: browser_rows)
    monkeypatch.setattr(fmkorea, "should_keep_row_by_time", lambda row, now, since: True)

    rows, security_blocked = fmkorea.collect_recent_rows(object(), now, since, [])

    assert rows == browser_rows
    assert security_blocked is False


def test_fmkorea_browser_fallback_stops_at_fallback_page_cap(monkeypatch):
    now = fmkorea.datetime(2026, 6, 3, 12, 0, tzinfo=fmkorea.KST)
    since = now - fmkorea.timedelta(hours=48)
    fetched = []
    extracted = []

    def fake_fetch(url):
        fetched.append(url)
        return [], True

    def fake_extract(page, url):
        extracted.append(url)
        return [{"href": "https://m.fmkorea.com/?mid=hotdeal&document_srl=101", "lines": [], "raw": ""}]

    monkeypatch.setattr(fmkorea, "fetch_static_page", fake_fetch)
    monkeypatch.setattr(fmkorea, "browser_fallback_enabled", lambda: True)
    monkeypatch.setattr(fmkorea, "run_page_extract", fake_extract)
    monkeypatch.setattr(fmkorea, "should_keep_row_by_time", lambda row, now, since: True)
    monkeypatch.setattr(fmkorea, "BROWSER_FALLBACK_MAX_PAGES", 1)

    rows, security_blocked = fmkorea.collect_recent_rows(object(), now, since, [])

    assert len(rows) == 1
    assert security_blocked is False
    assert len(fetched) == 1
    assert len(extracted) == 1
    assert "page=1" in extracted[0]


def test_fmkorea_security_backoff_uses_exponential_delay_with_jitter(monkeypatch):
    monkeypatch.setattr(fmkorea.random, "uniform", lambda low, high: 0)

    assert fmkorea.backoff_delay_seconds(1) == 3600
    assert fmkorea.backoff_delay_seconds(2) == 7200
    assert fmkorea.backoff_delay_seconds(3) == 14400


def test_fmkorea_clear_backoff_prints_recovery_signal(monkeypatch, tmp_path, capsys):
    state_path = tmp_path / "fmkorea_backoff_state.json"
    state_path.write_text('{"failures": 2}', encoding="utf-8")
    monkeypatch.setattr(fmkorea, "BACKOFF_STATE_PATH", state_path)

    fmkorea.clear_backoff_state()

    captured = capsys.readouterr()
    assert "FMKOREA_BACKOFF_RECOVERED previousFailures=2" in captured.out


def test_fmkorea_backoff_readonly_does_not_clear_state(monkeypatch, tmp_path, capsys):
    state_path = tmp_path / "fmkorea_backoff_state.json"
    state_path.write_text('{"failures": 2}', encoding="utf-8")
    monkeypatch.setattr(fmkorea, "BACKOFF_STATE_PATH", state_path)
    monkeypatch.setattr(fmkorea, "backoff_readonly_enabled", lambda: True)

    if fmkorea.backoff_readonly_enabled():
        print("FMKOREA_BACKOFF_READONLY_SUCCESS")
    else:
        fmkorea.clear_backoff_state()

    captured = capsys.readouterr()
    assert "FMKOREA_BACKOFF_READONLY_SUCCESS" in captured.out
    assert json.loads(state_path.read_text(encoding="utf-8"))["failures"] == 2


def test_fmkorea_filters_previous_items_outside_48_hour_window():
    now = fmkorea.datetime(2026, 6, 9, 12, 0, tzinfo=fmkorea.KST)
    since = now - fmkorea.timedelta(hours=48)
    items = [
        {"id": "recent", "registeredAt": "2026-06-08T10:00:00+09:00"},
        {"id": "old", "registeredAt": "2026-06-05T10:00:00+09:00"},
    ]

    filtered = fmkorea.filter_items_within_window(items, now, since)

    assert [item["id"] for item in filtered] == ["recent"]


def test_quasar_reuses_cached_detail_fields_by_post_id():
    cached = {
        "id": "98765",
        "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/98765",
        "img": "https://img.example/quasar.webp",
        "buyLink": "https://shop.example/quasar",
        "desc": "퀘이사 상세 본문",
        "registeredAt": "2026-06-02T12:34:00+09:00",
        "date": "2026-06-02",
    }
    lookup = quasar.build_previous_detail_lookup([cached])
    row = {
        "id": "98765",
        "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/98765?page=2",
        "img": "",
        "buyLink": "",
        "desc": "",
    }

    reused = quasar.apply_cached_detail_fields(row, lookup)

    assert reused is True
    assert row["img"] == cached["img"]
    assert row["buyLink"] == cached["buyLink"]
    assert row["desc"] == cached["desc"]
    assert row["registeredAt"] == cached["registeredAt"]


def test_quasar_does_not_skip_when_cached_registered_at_is_missing():
    lookup = quasar.build_previous_detail_lookup([
        {
            "id": "98765",
            "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/98765",
            "buyLink": "https://shop.example/quasar",
            "desc": "퀘이사 상세 본문",
        }
    ])
    row = {"id": "98765", "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/98765"}

    assert quasar.apply_cached_detail_fields(row, lookup) is False
    assert "registeredAt" not in row


def test_ppomppu_page_tail_seen_by_previous_bbs_no():
    previous_keys = ppomppu.build_previous_link_keys([
        {"sourceLink": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=708780"}
    ])
    row = {"href": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&page=2&no=708780"}

    assert ppomppu.row_exists_in_previous(row, previous_keys) is True


def test_ppomppu_page_tail_sample_seen_by_previous_bbs_no():
    previous_keys = ppomppu.build_previous_link_keys([
        {"sourceLink": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=708779"}
    ])
    rows = [
        {"href": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=708781"},
        {"href": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=708780"},
        {"href": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=708779"},
        {"href": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=708778"},
    ]

    assert ppomppu.page_tail_seen_in_previous(rows, previous_keys) is True


def test_quasar_page_tail_seen_by_previous_post_id():
    previous_keys = quasar.build_previous_link_keys([
        {"id": "98765", "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/98765"}
    ])
    row = {"id": "98765", "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/98765?page=2"}

    assert quasar.row_exists_in_previous(row, previous_keys) is True


def test_quasar_page_tail_sample_seen_by_previous_post_id():
    previous_keys = quasar.build_previous_link_keys([
        {"id": "98764", "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/98764"}
    ])
    rows = [
        {"id": "98766", "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/98766"},
        {"id": "98765", "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/98765"},
        {"id": "98764", "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/98764"},
        {"id": "98763", "sourceLink": "https://quasarzone.com/bbs/qb_saleinfo/views/98763"},
    ]

    assert quasar.page_tail_seen_in_previous(rows, previous_keys) is True


def test_ruliweb_page_tail_seen_by_previous_source_link():
    from scripts import update_ruliweb_feed as ruliweb

    previous_keys = ruliweb.build_previous_link_keys([
        {"sourceLink": "https://m.ruliweb.com/market/board/1020/read/123456"}
    ])
    row = {"sourceLink": "https://m.ruliweb.com/market/board/1020/read/123456"}

    assert ruliweb.row_exists_in_previous(row, previous_keys) is True


def test_ruliweb_page_tail_sample_seen_by_previous_source_link():
    from scripts import update_ruliweb_feed as ruliweb

    previous_keys = ruliweb.build_previous_link_keys([
        {"sourceLink": "https://m.ruliweb.com/market/board/1020/read/123455"}
    ])
    rows = [
        {"sourceLink": "https://m.ruliweb.com/market/board/1020/read/123457"},
        {"sourceLink": "https://m.ruliweb.com/market/board/1020/read/123456"},
        {"sourceLink": "https://m.ruliweb.com/market/board/1020/read/123455"},
        {"sourceLink": "https://m.ruliweb.com/market/board/1020/read/123454"},
    ]

    assert ruliweb.page_tail_seen_in_previous(rows, previous_keys) is True


def test_ppomppu_reuses_cached_detail_fields_by_bbs_no():
    cached = {
        "sourceLink": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=708780",
        "title": "캐시된 뽐뿌 딜",
        "registeredAt": "2026-06-02T12:34:00+09:00",
        "date": "2026-06-02",
        "desc": "이미 파싱한 뽐뿌 상세 본문",
        "img": "https://img.example/ppomppu.webp",
        "buyLink": "https://shop.example/ppomppu",
        "likes": 7,
    }
    lookup = ppomppu.build_previous_detail_lookup([cached])
    row = {"href": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&page=2&no=708780"}

    reused = ppomppu.apply_cached_detail_fields(row, lookup)

    assert reused is True
    assert row["title"] == cached["title"]
    assert row["buyLink"] == cached["buyLink"]
    assert row["registeredAt"] == cached["registeredAt"]


def test_fmkorea_parses_full_ymd_date_token():
    now = fmkorea.datetime(2026, 6, 3, 3, 50, tzinfo=fmkorea.KST)

    parsed = fmkorea.parse_time_token("2026.06.01", now)

    assert parsed.isoformat() == "2026-06-01T00:00:00+09:00"


def test_quasar_ignores_future_sale_date_when_extracting_registered_at():
    now = quasar.datetime(2026, 6, 3, 3, 50, tzinfo=quasar.KST)
    detail_html = """
    <div>행사기간 2026.06.03 22:00</div>
    <div>작성일 2026.06.02 18:15</div>
    """

    registered_at = quasar.extract_registered_at_from_detail(detail_html, "2026-06-02", now=now)

    assert registered_at == "2026-06-02T18:15:00+09:00"


def test_fmkorea_treats_future_hhmm_as_yesterday():
    now = fmkorea.datetime(2026, 6, 3, 3, 50, tzinfo=fmkorea.KST)

    parsed = fmkorea.parse_time_token("23:37", now)

    assert parsed.isoformat() == "2026-06-02T23:37:00+09:00"
