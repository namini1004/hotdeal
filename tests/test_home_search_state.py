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

    assert "const SEARCH_QUERY_KEY = 'hotdeal_home_search_query_v1';" in html
    assert "const SEARCH_RESTORE_PENDING_KEY = 'hotdeal_home_search_restore_pending_v1';" in html
    assert "function saveSearchStateForDetailReturn()" in html
    assert "sessionStorage.setItem(SEARCH_QUERY_KEY, input?.value || state.keyword || '');" in html
    assert "sessionStorage.setItem(SEARCH_RESTORE_PENDING_KEY, '1');" in html
    assert "function restoreSearchStateForDetailReturn()" in html
    assert "input.value = sessionStorage.getItem(SEARCH_QUERY_KEY) || '';" in html
    assert "function syncSearchStateFromInput()" in html
    assert "const nextKeyword = input.value || '';" in html
    assert "state.keyword = nextKeyword;" in html
    assert "window.addEventListener('pageshow', () => {\n        restoreSearchStateForDetailReturn();\n        syncSearchStateFromInput();\n        render();" in html
    assert "saveListScrollState();\n        saveSearchStateForDetailReturn();" in html
    assert "if(syncSearchStateFromInput()) render();" in html


def test_clear_button_is_the_only_explicit_search_reset():
    html = read_index()

    clear_handler = html.split("clear.addEventListener('click', () => {", 1)[1].split("});", 1)[0]
    assert "input.value = '';" in clear_handler
    assert "sessionStorage.removeItem(SEARCH_QUERY_KEY);" in clear_handler
    assert "sessionStorage.removeItem(SEARCH_RESTORE_PENDING_KEY);" in clear_handler
