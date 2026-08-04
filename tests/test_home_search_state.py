from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_index():
    return (ROOT / "index.html").read_text(encoding="utf-8")


def test_search_has_clear_control_and_resets_filter_state():
    html = read_index()

    assert 'id="searchClear"' in html
    assert 'aria-label="검색어 지우기"' in html
    assert "input.value = '';" in html
    assert "clear.hidden = nextKeyword.length === 0;" in html
    assert "syncSearchStateFromInput();\n        render();\n        input.focus();" in html


def test_restored_search_input_is_reapplied_on_page_resume():
    html = read_index()

    assert "function syncSearchStateFromInput()" in html
    assert "const nextKeyword = input.value || '';" in html
    assert "state.keyword = nextKeyword;" in html
    assert "window.addEventListener('pageshow', () => {\n        syncSearchStateFromInput();\n        render();" in html
    assert "if(syncSearchStateFromInput()) render();" in html
