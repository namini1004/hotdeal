from scripts import update_fmkorea_feed as fmkorea
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
