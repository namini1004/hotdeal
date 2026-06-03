#!/usr/bin/env python3
import html
import re
from typing import Dict

POSITIVE_COMMENT_KEYWORDS = [
    '역대가',
    '역대급',
    '대박급',
    '삽니다',
    '사야겠네요',
    '감사합니다',
    '고맙습니다',
]

NEGATIVE_COMMENT_KEYWORDS = [
    '바이럴업체',
    '바이럴',
    '업체',
    '업자',
    '비싸다',
    '비싸네요',
    '비싸네',
    '비쌈',
    '안사요',
    '안 사요',
    '응 안사',
    '응 안 사',
]


def strip_html_text(value: str) -> str:
    text = re.sub(r'<script[\s\S]*?</script>', ' ', value or '', flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', ' ', text, flags=re.I)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def count_keyword_hits(text: str, keywords) -> int:
    return sum(len(re.findall(re.escape(keyword), text, flags=re.I)) for keyword in keywords)


def analyze_comment_quality(comment_html_or_text: str) -> Dict[str, int]:
    """댓글 키워드 기반 온도 보정값을 계산한다.

    긍정은 +2점, 부정은 -8점으로 잡아 바이럴/업체/비싸다/안사요 류 신호가
    온도를 매우 강하게 낮추도록 한다. 극단값은 -60~+16으로 제한해 부정 신호가
    최신성/댓글수보다 우선 반영되게 한다.
    """
    text = strip_html_text(comment_html_or_text)
    positive_count = count_keyword_hits(text, POSITIVE_COMMENT_KEYWORDS)
    negative_count = count_keyword_hits(text, NEGATIVE_COMMENT_KEYWORDS)
    raw_score = positive_count * 2 - negative_count * 8
    score = max(-60, min(16, raw_score))
    return {
        'positiveCount': positive_count,
        'negativeCount': negative_count,
        'score': score,
    }
