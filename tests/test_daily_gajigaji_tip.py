import unittest
from datetime import datetime, timedelta, timezone

from scripts import post_daily_gajigaji_tip as tips


NOW = datetime(2026, 8, 17, 0, 0, tzinfo=timezone.utc)


def make_source(url="https://www.youtube.com/watch?v=new-source"):
    return tips.SourceCandidate(
        channel="노써치",
        title="새 제품 구매 가이드",
        url=url,
        published_at=NOW - timedelta(days=1),
        thumbnail_url="https://i.ytimg.com/vi/new-source/hqdefault.jpg",
        description="",
    )


def make_draft(**overrides):
    body = (
        "# 충전기는 숫자보다 포트 구성이 먼저다\n\n"
        "충전기를 고를 때 최대 출력만 보면 실제 사용에서 불편할 수 있습니다. "
        "매일 함께 충전하는 기기 수와 케이블 위치를 먼저 정하면 필요한 구성이 선명해집니다. "
        "노트북과 휴대폰을 동시에 연결했을 때 출력이 어떻게 나뉘는지도 확인해야 합니다.\n\n"
        "책상에서 쓸 제품이라면 플러그 방향과 본체 폭도 살펴보는 편이 좋습니다. "
        "출력이 충분해도 옆 콘센트를 가리거나 케이블이 짧으면 매일 위치를 바꾸게 됩니다. "
        "여행용이라면 접이식 플러그와 전체 무게가 체감 편의에 더 큰 영향을 줄 수 있습니다. "
        "보유한 기기가 요구하는 충전 규격을 먼저 적고, 그 조합을 동시에 감당하는지를 비교하면 "
        "쓰지 않을 고출력에 비용을 더 내는 일을 줄일 수 있습니다.\n\n"
        "구매 전 체크:\n"
        "- 자주 충전하는 기기 수\n"
        "- USB-C 포트별 최대 출력\n"
        "- 동시 연결 시 출력 배분\n"
        "- 케이블 포함 여부와 길이\n"
        "- 콘센트에서 차지하는 공간\n\n"
        "충전 중 발열이 걱정된다면 책이나 천 위를 피하고 통풍되는 자리에 둘 수 있는 크기인지도 "
        "함께 생각하세요. 판매 페이지의 단일 포트 수치와 여러 포트를 쓸 때의 수치는 다를 수 있으니 "
        "동시 출력표를 확인하는 습관이 중요합니다.\n\n"
        "한 줄 팁: 가장 큰 숫자보다 매일 꽂을 조합에 맞는 충전기가 오래 쓰기 편합니다."
    )
    draft = {
        "title": "충전기는 숫자보다 포트 구성이 먼저다",
        "product": "충전기",
        "body": body,
        "source_url": "https://www.youtube.com/watch?v=new-source",
    }
    draft.update(overrides)
    return draft


class DailyGajigajiTipTests(unittest.TestCase):
    def test_similarity_removes_generated_date_suffixes(self):
        original = "모니터는 해상도보다 놓는 거리부터 정해야 한다"
        repeated = "모니터는 해상도보다 놓는 거리부터 정해야 한다 (20260816)"

        self.assertEqual(tips.text_similarity(original, repeated), 1.0)

    def test_validate_draft_rejects_reused_title_body_source_and_product(self):
        source = make_source()
        draft = make_draft()
        posts = [
            {
                "title": draft["title"],
                "body": f"{draft['body']}\n\n## 참고 자료\n- [기존]({source.url})",
                "author": "가지딜",
                "createdAt": (NOW - timedelta(days=3)).isoformat(),
            }
        ]

        reasons = tips.validate_draft(draft, posts, {source.url: source}, NOW)

        self.assertTrue(any(reason.startswith("similar_title:") for reason in reasons))
        self.assertTrue(any(reason.startswith("similar_body:") for reason in reasons))
        self.assertIn("source_already_used", reasons)
        self.assertTrue(any(reason.startswith("product_cooldown:") for reason in reasons))

    def test_validate_draft_accepts_original_trusted_content(self):
        source = make_source()

        reasons = tips.validate_draft(make_draft(), [], {source.url: source}, NOW)

        self.assertEqual(reasons, [])

    def test_product_cooldown_uses_core_name_without_generic_modifier(self):
        posts = [
            {
                "title": "선풍기, 예쁜 디자인보다 먼저 봐야 할 3가지",
                "body": "짧은 기존 글",
                "createdAt": (NOW - timedelta(days=77)).isoformat(),
            }
        ]

        conflict = tips.recent_product_conflict("무선 선풍기", posts, NOW)

        self.assertEqual(conflict, posts[0]["title"])

    def test_product_cooldown_ignores_posts_outside_window(self):
        posts = [
            {
                "title": "선풍기, 예쁜 디자인보다 먼저 봐야 할 3가지",
                "body": "짧은 기존 글",
                "createdAt": (NOW - timedelta(days=121)).isoformat(),
            }
        ]

        self.assertEqual(tips.recent_product_conflict("무선 선풍기", posts, NOW), "")

    def test_build_payload_restores_old_author_photo_and_source_style(self):
        source = make_source()

        payload = tips.build_payload(make_draft(), source)

        self.assertEqual(payload["author"], "가지딜")
        self.assertEqual(payload["img"], source.thumbnail_url)
        self.assertTrue(payload["body"].startswith("<!--gaji-category:tips-->\n# 충전기는"))
        self.assertIn(f"]({source.url})", payload["body"])

    def test_today_guard_accepts_only_one_automation_post_per_kst_day(self):
        posts = [
            {
                "author": "가지딜",
                "createdAt": "2026-08-16T15:30:00+00:00",
            }
        ]

        self.assertTrue(tips.has_automation_post_today(posts, NOW))


if __name__ == "__main__":
    unittest.main()
