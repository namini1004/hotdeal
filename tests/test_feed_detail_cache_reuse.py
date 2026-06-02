from scripts import update_fmkorea_feed as fmkorea
from scripts import update_ppomppu_feed as ppomppu
from scripts import update_quasar_feed as quasar


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
