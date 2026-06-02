from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "index.html"


def read_index():
    return INDEX_HTML.read_text(encoding="utf-8")


def test_home_tabs_use_deal_labels_and_keep_view_toggle_next_to_chips():
    html = read_index()

    controls_start = html.index('<div class="feed-controls">')
    controls_end = html.index('</header>', controls_start)
    controls = html[controls_start:controls_end]

    assert 'data-tab="all">전체딜</button>' in controls
    assert 'data-tab="popular">인기딜</button>' in controls
    assert 'data-tab="latest">최신딜</button>' in controls
    assert 'data-tab="pick">가지딜</button>' in controls
    assert controls.index('id="tabs"') < controls.index('class="view-toggle"')
    assert 'aria-label="바둑판 보기"' in controls
    assert 'aria-label="리스트 보기"' in controls


def test_view_toggle_is_visible_on_mobile_and_app_webview():
    html = read_index()

    # The toggle should be a mobile/app control too, not desktop-only.
    assert '.view-toggle{display:flex' in html
    assert '.view-toggle{display:none' not in html
    assert '.app-webview .view-toggle' in html
    assert 'grid-template-columns:54px minmax(0,1fr)' in html
    assert '.list.view-list .thumb{width:54px;height:54px' in html


def test_desktop_list_mode_remains_compact_board_style():
    html = read_index()
    desktop_start = html.index('@media (min-width:768px)')
    desktop_end = html.index('@media (min-width:1180px)', desktop_start)
    desktop_css = html[desktop_start:desktop_end]

    assert '.list.view-list{grid-template-columns:minmax(0,1fr)' in desktop_css
    assert '.list.view-list .item{grid-template-columns:44px minmax(0,1fr)' in desktop_css
    assert '.list.view-list .thumb{width:44px;height:44px' in desktop_css
