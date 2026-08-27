#!/usr/bin/env python3
import html
import re
from html.parser import HTMLParser
from typing import Dict


QUALITY_SIGNAL_PARSER_VERSION = 2

COMMENT_ROOT_PATTERN = re.compile(
    r'(?:^|[\s_-])(?:comment|comments|reply|replies|memo|fdb|fdb-lst|fdb_lst)(?:$|[\s_-])',
    re.I,
)
COMMENT_NON_BODY_PATTERN = re.compile(
    r'(?:count|counter|button|form|write|input|pagination|paging|more|header|title|toggle)',
    re.I,
)

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


class CommentSectionTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.capture_depth = 0
        self.skip_depth = 0
        self.parts = []

    @staticmethod
    def _is_comment_root(attrs) -> bool:
        values = []
        for key, value in attrs:
            if key.lower() in {'id', 'class'} and value:
                values.append(str(value).lower())
        marker = ' '.join(values)
        if not marker or COMMENT_NON_BODY_PATTERN.search(marker):
            return False
        return bool(COMMENT_ROOT_PATTERN.search(marker.replace('__', '_')))

    def handle_starttag(self, tag, attrs):
        tag = str(tag or '').lower()
        if self.capture_depth:
            self.capture_depth += 1
            if self.skip_depth:
                self.skip_depth += 1
            elif tag in {'script', 'style', 'template'}:
                self.skip_depth = 1
            return
        if self._is_comment_root(attrs):
            self.capture_depth = 1
            if tag in {'script', 'style', 'template'}:
                self.skip_depth = 1

    def handle_startendtag(self, tag, attrs):
        if self.capture_depth and not self.skip_depth and str(tag or '').lower() == 'br':
            self.parts.append('\n')

    def handle_endtag(self, _tag):
        if not self.capture_depth:
            return
        if self.skip_depth:
            self.skip_depth -= 1
        self.capture_depth -= 1
        if not self.capture_depth:
            self.parts.append('\n')

    def handle_data(self, data):
        if self.capture_depth and not self.skip_depth:
            value = str(data or '').strip()
            if value:
                self.parts.append(value)

    def text(self) -> str:
        return re.sub(r'\s+', ' ', ' '.join(self.parts)).strip()


def extract_comment_signal_text(detail_html: str) -> str:
    """상세 페이지의 댓글 컨테이너 안쪽 텍스트만 반환한다.

    댓글 컨테이너를 찾지 못하면 본문을 대신 분석하지 않고 빈 문자열을
    반환한다. 본문/내비게이션의 단어가 부정 댓글로 오인되는 것보다
    중립 신호로 두는 편이 안전하다.
    """
    parser = CommentSectionTextParser()
    try:
        parser.feed(detail_html or '')
        parser.close()
    except Exception:
        return ''
    return parser.text()


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
