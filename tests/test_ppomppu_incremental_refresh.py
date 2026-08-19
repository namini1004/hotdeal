import os
from datetime import datetime, timedelta
from unittest.mock import patch

from scripts import update_ppomppu_feed as ppomppu


class FakeResponse:
    def __init__(self, *, text='', json_data=None):
        self.text = text
        self._json_data = json_data

    def raise_for_status(self):
        return None

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self, detail_html):
        self.headers = {}
        self.detail_html = detail_html
        self.calls = []

    def get(self, url, timeout):
        self.calls.append((url, timeout))
        if url == ppomppu.LIST_URL:
            return FakeResponse(text='<html>list</html>')
        return FakeResponse(text=self.detail_html)


class FailingListSession:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout):
        raise ppomppu.requests.HTTPError('blocked')


def cached_item(no, title, registered_at):
    date_label = registered_at[:10]
    return {
        'id': no,
        'title': title,
        'area': '뽐뿌 핫딜',
        'dist': '기타',
        'time': date_label,
        'registeredAt': registered_at,
        'price': '1,000원',
        'likes': 1,
        'dislikes': 0,
        'views': 10,
        'comments': 1,
        'commentSignalScore': 0,
        'positiveCommentSignals': 0,
        'negativeCommentSignals': 0,
        'category': '기타',
        'desc': 'cached description',
        'img': 'https://example.com/cached.jpg',
        'buyLink': '',
        'sourceLink': f'https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no={no}',
        'source': 'ppomppu',
        'date': date_label,
    }


def test_remote_cache_maps_supabase_rows_to_feed_items():
    registered_at = datetime.now(ppomppu.KST).replace(microsecond=0).isoformat()
    response = FakeResponse(json_data=[{
        'id': 'db-id',
        'title': 'cached deal',
        'area': '뽐뿌 핫딜',
        'category': '식품',
        'date': registered_at[:10],
        'registered_at': registered_at,
        'price': '2,000원',
        'likes': 3,
        'dislikes': 0,
        'views': 20,
        'comments': 2,
        'comment_signal_score': 1,
        'positive_comment_signals': 1,
        'negative_comment_signals': 0,
        'desc': 'remote description',
        'img': 'https://example.com/remote.jpg',
        'buy_link': 'https://shop.example.com',
        'source_link': 'https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=100',
    }])

    with patch.dict(os.environ, {
        'SUPABASE_URL': 'https://example.supabase.co',
        'SUPABASE_SERVICE_ROLE_KEY': 'service-key',
    }), patch.object(ppomppu.requests, 'get', return_value=response) as request:
        items = ppomppu.load_remote_previous_items()

    assert len(items) == 1
    assert items[0]['registeredAt'] == registered_at
    assert items[0]['desc'] == 'remote description'
    assert items[0]['sourceLink'].endswith('no=100')
    assert request.call_args.kwargs['params']['source'] == 'eq.ppomppu'
    assert request.call_args.kwargs['params']['deleted_at'] == 'is.null'


def test_page_one_refresh_fetches_only_new_details_and_preserves_previous_window():
    now = datetime.now(ppomppu.KST).replace(second=0, microsecond=0)
    cached_on_page = cached_item('101', 'known deal', (now - timedelta(minutes=20)).isoformat())
    cached_off_page = cached_item('100', 'older retained deal', (now - timedelta(hours=4)).isoformat())
    new_link = 'https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=102'
    rows = [
        {
            'href': cached_on_page['sourceLink'],
            'raw_title': cached_on_page['title'],
            'img': '',
            'category': '기타',
            'views': 10,
            'comments': 1,
            'likes': 1,
        },
        {
            'href': new_link,
            'raw_title': '[테스트] new deal',
            'img': '',
            'category': '테스트',
            'views': 5,
            'comments': 0,
            'likes': 0,
        },
    ]
    detail_html = f'''
      <meta property="og:title" content="[테스트] new deal (3,000원/무료)">
      <span class="hi">{now.strftime('%Y-%m-%d %H:%M')}</span>
      <div id="KH_Content"><p>new description</p></div>
      <section id="recommend"><span class="up-numb">2</span></section>
    '''
    session = FakeSession(detail_html)

    with patch.object(ppomppu, 'parse_list_rows', return_value=rows), patch.object(
        ppomppu,
        'load_hidden_hotdeals',
        return_value={'sourceLinks': set(), 'bbsNos': set()},
    ):
        data = ppomppu.parse_items(
            session=session,
            previous_items=[cached_on_page, cached_off_page],
        )

    links = {item['sourceLink'] for item in data['items']}
    assert links == {cached_on_page['sourceLink'], cached_off_page['sourceLink'], new_link}
    assert [call[0] for call in session.calls] == [ppomppu.LIST_URL, new_link]
    assert data['counts']['total'] == 3


def test_list_failure_keeps_current_cached_window_instead_of_emptying_feed():
    now = datetime.now(ppomppu.KST).replace(second=0, microsecond=0)
    previous = cached_item('100', 'retained deal', (now - timedelta(hours=1)).isoformat())

    with patch.object(
        ppomppu,
        'load_hidden_hotdeals',
        return_value={'sourceLinks': set(), 'bbsNos': set()},
    ):
        data = ppomppu.parse_items(
            session=FailingListSession(),
            previous_items=[previous],
        )

    assert data['counts']['total'] == 1
    assert data['items'][0]['sourceLink'] == previous['sourceLink']
