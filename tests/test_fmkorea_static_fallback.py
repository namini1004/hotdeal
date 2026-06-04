from datetime import datetime, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from update_fmkorea_feed import KST, parse_static_html_rows, should_keep_row_by_time


def test_parse_static_fmkorea_webzine_rows_extracts_deal_fields():
    html = '''
    <ul>
      <li class="li  li_best2_hotdeal0"><div class="li">
        <a href="/index.php?mid=hotdeal&amp;listStyle=webzine&amp;document_srl=9913747903">
          <img class="thumb" src="//image.fmkorea.com/classes/lazy/img/transparent.gif" data-original="//image.fmkorea.com/filesn/cache/thumb/20260604/9913747903_70x50.crop.webp" />
        </a>
        <h3 class="title"><a href="/index.php?mid=hotdeal&amp;listStyle=webzine&amp;document_srl=9913747903"><span class="ellipsis-target">AJAZZ 풀알루미늄 키보드</span></a></h3>
        <div class="hotdeal_info"><span>쇼핑몰: <a>dillik</a></span> / <span>가격: <a>43,900원</a></span> / <span>배송: <a>무료</a></span></div>
        <div><span class="category"><a>기타</a> / </span><span class="regdate">20:18</span><span class="author"> / vo0ov</span></div>
        <a class="pc_voted_count"><span class="label">추천 </span><span class="count">12</span></a>
      </div></li>
    </ul>
    '''
    rows = parse_static_html_rows(html, 'https://www.fmkorea.com/index.php?mid=hotdeal&listStyle=webzine&page=1')
    assert len(rows) == 1
    row = rows[0]
    assert row['title'] == 'AJAZZ 풀알루미늄 키보드'
    assert row['href'] == 'https://www.fmkorea.com/index.php?mid=hotdeal&listStyle=webzine&document_srl=9913747903'
    assert row['img'].startswith('https://image.fmkorea.com/filesn/cache/thumb/')
    assert '쇼핑몰: dillik / 가격: 43,900원 / 배송: 무료' in row['lines']
    assert '기타 / 20:18 / 추천 12 / 조회 0' in row['lines']
    assert row['_listParser'] == 'static'

    now = datetime(2026, 6, 4, 20, 30, tzinfo=KST)
    assert should_keep_row_by_time(row, now, now - timedelta(hours=48))


def test_parse_static_fmkorea_security_page_returns_empty():
    rows = parse_static_html_rows('<title>에펨코리아 보안 시스템</title>', 'https://www.fmkorea.com/')
    assert rows == []
