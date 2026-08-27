from scripts import update_ruliweb_feed as ruliweb


def test_ruliweb_rich_body_preserves_safe_source_formatting():
    detail_html = '''
    <html><body>
      <div class="view_content autolink">
        <p style="text-align: center;">첫 문단<br>둘째 줄</p>
        <div style="text-align:center">
          <span style="font-size: 24px;"><b>할인코드</b></span>
        </div>
        <div style="text-align:center"><b>19달러 이상 구매</b></div>
        <div><div>중첩 본문</div></div>
        <p>마지막 본문</p>
      </div>
      <div id="outside">본문 밖 문구</div>
    </body></html>
    '''

    desc = ruliweb.extract_body_text(detail_html)

    assert desc.startswith(ruliweb.RICH_TEXT_PREFIX)
    assert '<p class="gaji-align-center">첫 문단<br>둘째 줄</p>' in desc
    assert '<span class="gaji-text-xl"><strong>할인코드</strong></span>' in desc
    assert '<div class="gaji-align-center"><strong>19달러 이상 구매</strong></div>' in desc
    assert '중첩 본문' in desc
    assert '마지막 본문' in desc
    assert '본문 밖 문구' not in desc


def test_ruliweb_rich_body_drops_unsafe_markup_and_arbitrary_styles():
    detail_html = '''
    <div class="view_content">
      <p style="position:fixed;color:red;text-align:right" onclick="steal()">안전한 문구</p>
      <script>alert('xss')</script>
      <img src="x" onerror="steal()">
      <a href="javascript:steal()" style="font-size:99px">링크 문구</a>
    </div>
    '''

    desc = ruliweb.extract_body_text(detail_html)

    assert 'gaji-align-right' in desc
    assert '안전한 문구' in desc
    assert '링크 문구' in desc
    assert 'script' not in desc
    assert 'alert(' not in desc
    assert '<img' not in desc
    assert 'onerror' not in desc
    assert 'onclick' not in desc
    assert 'javascript:' not in desc
    assert 'position:' not in desc
    assert 'color:' not in desc


def test_ruliweb_content_chunk_balances_nested_divs():
    detail_html = '''
    <div class="before">앞</div>
    <div data-id="1" class="foo view_content bar">
      <div><div>안쪽</div></div>
      <p>꼬리 본문</p>
    </div>
    <div class="after">뒤</div>
    '''

    chunk = ruliweb.get_content_chunk(detail_html)

    assert '안쪽' in chunk
    assert '꼬리 본문' in chunk
    assert 'class="after"' not in chunk
