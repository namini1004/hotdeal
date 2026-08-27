import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(relative_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ppomppu_recommend_box_parses_up_and_down_counts():
    ppomppu = load_module('scripts/update_ppomppu_feed.py', 'ppomppu_feed')
    html = '''
      <div id="recommend">
        <span class="up-numb"> 1,234 </span>
        <span class="down-numb"> 56 </span>
      </div>
    '''
    assert ppomppu.parse_recommend_counts(html) == (1234, 56)


def test_ruliweb_like_value_parses_detail_like_count():
    ruliweb = load_module('scripts/update_ruliweb_feed.py', 'ruliweb_feed')
    html = '<div><span class="like-value"> 89 </span></div>'
    assert ruliweb.parse_detail_like_count(html) == 89


def test_fmkorea_voted_count_parses_detail_recommend_value():
    fmkorea = load_module('scripts/update_fmkorea_feed.py', 'fmkorea_feed')
    html = '<input class="btn_img new_voted_count" value="321">'
    assert fmkorea.parse_detail_voted_count(html) == 321


def test_comment_keyword_score_adds_positive_and_subtracts_negative_signals():
    signals = load_module('scripts/hotdeal_quality_signals.py', 'hotdeal_quality_signals')
    html = '''
      <ul class="comments">
        <li>역대가네요. 삽니다 감사합니다</li>
        <li>바이럴 같고 업자 냄새납니다. 비싸다</li>
      </ul>
    '''
    result = signals.analyze_comment_quality(html)
    assert result['positiveCount'] == 3
    assert result['negativeCount'] == 3
    assert result['score'] < 0


def test_comment_keyword_score_strongly_penalizes_viral_expensive_and_no_buy_phrases():
    signals = load_module('scripts/hotdeal_quality_signals.py', 'hotdeal_quality_signals')
    html = '''
      <ul class="comments">
        <li>바이럴업체 같은데요</li>
        <li>비싸네요. 응 안사</li>
        <li>안사요</li>
      </ul>
    '''
    result = signals.analyze_comment_quality(html)
    assert result['negativeCount'] >= 5
    assert result['score'] <= -25


def test_comment_signal_extractor_ignores_article_body_and_reads_comments_only():
    signals = load_module('scripts/hotdeal_quality_signals.py', 'hotdeal_quality_signals_comment_scope')
    html = '''
      <article>업체 바이럴 같고 비싸다 안사요라는 단어가 본문 예시에 있습니다.</article>
      <div class="comment-count">댓글 2</div>
      <ul class="comment-list">
        <li>역대가네요. 감사합니다.</li>
        <li>사야겠네요.</li>
      </ul>
    '''
    comment_text = signals.extract_comment_signal_text(html)
    result = signals.analyze_comment_quality(comment_text)
    assert '바이럴' not in comment_text
    assert result['positiveCount'] == 3
    assert result['negativeCount'] == 0


def test_comment_signal_extractor_returns_neutral_when_comment_container_is_missing():
    signals = load_module('scripts/hotdeal_quality_signals.py', 'hotdeal_quality_signals_no_comments')
    html = '<article>비싸다 바이럴 업체라서 안사요</article>'
    comment_text = signals.extract_comment_signal_text(html)
    assert comment_text == ''
    assert signals.analyze_comment_quality(comment_text)['score'] == 0


def test_api_canonical_feed_key_dedupes_ppomppu_page_variants():
    script = f'''
      const deals = require({json.dumps(str(ROOT / 'api/_lib/deals.js'))});
      const a = deals.canonicalFeedKey({{ source: 'ppomppu', sourceLink: 'https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&page=1&divpage=112&no=708770' }});
      const b = deals.canonicalFeedKey({{ source: 'ppomppu', sourceLink: 'https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&page=6&divpage=112&no=708770' }});
      console.log(JSON.stringify({{ a, b }}));
    '''
    out = subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True)
    data = json.loads(out)
    assert data['a'] == 'ppomppu::no:708770'
    assert data['a'] == data['b']


def test_api_canonical_feed_key_extracts_all_feed_source_ids():
    script = f'''
      const deals = require({json.dumps(str(ROOT / 'api/_lib/deals.js'))});
      const keys = [
        deals.canonicalFeedKey({{ source: 'ppomppu', sourceLink: 'https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&page=6&no=708770' }}),
        deals.canonicalFeedKey({{ source: 'quasar', sourceLink: 'https://quasarzone.com/bbs/qb_saleinfo/views/1960291?page=2' }}),
        deals.canonicalFeedKey({{ source: 'fmkorea', sourceLink: 'https://m.fmkorea.com/?mid=hotdeal&document_srl=9941127608' }}),
        deals.canonicalFeedKey({{ source: 'ruliweb', sourceLink: 'https://m.ruliweb.com/market/board/1020/read/104541' }}),
        deals.canonicalFeedKey({{ source: 'fmkorea', sourcePostId: '9941127608', sourceLink: 'https://example.com/changed' }}),
      ];
      console.log(JSON.stringify(keys));
    '''
    out = subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True)
    assert json.loads(out) == [
        'ppomppu::no:708770',
        'quasar::view:1960291',
        'fmkorea::doc:9941127608',
        'ruliweb::read:104541',
        'fmkorea::post:9941127608',
    ]


def test_api_feed_duplicate_prefers_row_with_image_over_newer_blank():
    script = f'''
      const deals = require({json.dumps(str(ROOT / 'api/_lib/deals.js'))});
      const withImage = {{
        source: 'quasar',
        sourceLink: 'https://quasarzone.com/bbs/qb_saleinfo/views/98765',
        img: 'https://img.example/thumb.webp',
        updatedAt: '2026-06-09T01:00:00Z'
      }};
      const blankNewer = {{
        source: 'quasar',
        sourceLink: 'https://quasarzone.com/bbs/qb_saleinfo/views/98765',
        img: '',
        detailImg: '',
        updatedAt: '2026-06-09T02:00:00Z'
      }};
      console.log(JSON.stringify({{
        replaceImageWithBlank: deals.shouldReplaceFeedDuplicate(withImage, blankNewer),
        replaceBlankWithImage: deals.shouldReplaceFeedDuplicate(blankNewer, withImage)
      }}));
    '''
    out = subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True)
    data = json.loads(out)
    assert data['replaceImageWithBlank'] is False
    assert data['replaceBlankWithImage'] is True


def test_temperature_weights_recommendations_dislikes_and_comment_signals():
    script = f'''
      const deals = require({json.dumps(str(ROOT / 'api/_lib/deals.js'))});
      const now = Date.parse('2026-06-03T12:00:00+09:00');
      const base = {{ views: 100, comments: 5, registeredAt: '2026-06-03T10:00:00+09:00', source: 'ppomppu' }};
      const liked = deals.computeHotScore({{ ...base, likes: 40, dislikes: 0, commentSignalScore: 8 }}, now, {{ views: 100, comments: 5 }});
      const disliked = deals.computeHotScore({{ ...base, likes: 40, dislikes: 10, commentSignalScore: -8 }}, now, {{ views: 100, comments: 5 }});
      console.log(JSON.stringify({{ liked, disliked }}));
    '''
    out = subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True)
    data = json.loads(out)
    assert data['liked'] > data['disliked']
    assert data['liked'] - data['disliked'] >= 8


def test_temperature_caps_at_50_when_negative_comments_or_dislikes_reach_three():
    script = f'''
      const deals = require({json.dumps(str(ROOT / 'api/_lib/deals.js'))});
      const items = [
        {{ id: 'good', source: 'ppomppu', price: '10,000원', views: 100, comments: 1, likes: 0, dislikes: 0, commentSignalScore: 0, negativeCommentSignals: 0, registeredAt: '2026-06-01T10:00:00+09:00' }},
        {{ id: 'negative-comments', source: 'ppomppu', price: '무료', views: 999999, comments: 999, likes: 999, dislikes: 0, commentSignalScore: -30, negativeCommentSignals: 3, registeredAt: new Date().toISOString() }},
        {{ id: 'disliked', source: 'ppomppu', price: '10,000원', views: 999999, comments: 999, likes: 999, dislikes: 3, commentSignalScore: 0, negativeCommentSignals: 0, registeredAt: new Date().toISOString() }},
      ];
      const result = deals.applyTemperatureNormalization(items);
      console.log(JSON.stringify(Object.fromEntries(result.map((item) => [item.id, item.temperature]))));
    '''
    out = subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True)
    data = json.loads(out)
    assert data['negative-comments'] <= 50
    assert data['disliked'] <= 50


def test_temperature_ignores_source_wide_contaminated_negative_caps_without_deleting_data():
    script = f'''
      const deals = require({json.dumps(str(ROOT / 'api/_lib/deals.js'))});
      const items = Array.from({{ length: 20 }}, (_, index) => ({{
        id: String(index), source: 'legacy-parser', views: 100 + index * 100,
        comments: index, negativeCommentSignals: 5, commentSignalScore: -60,
        registeredAt: '2026-08-27T10:00:00Z'
      }}));
      const profile = deals.buildTemperatureProfile(items, Date.parse('2026-08-27T12:00:00Z'));
      const result = deals.applyTemperatureProfile(items, profile);
      console.log(JSON.stringify({{
        contaminated: profile.statsBySource.get('legacy-parser').qualitySignalsContaminated,
        max: Math.max(...result.map((item) => item.temperature))
      }}));
    '''
    out = subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True)
    data = json.loads(out)
    assert data['contaminated'] is True
    assert data['max'] > 50


def test_temperature_balances_source_scale_but_rewards_absolute_outliers():
    script = f'''
      const deals = require({json.dumps(str(ROOT / 'api/_lib/deals.js'))});
      const now = Date.parse('2026-08-27T12:00:00Z');
      const items = [];
      for (let index = 0; index < 20; index += 1) {{
        items.push({{
          id: `small-${{index}}`, source: 'small', views: 100 + index * 25,
          comments: index % 6, likes: 0, registeredAt: '2026-08-27T10:00:00Z'
        }});
        items.push({{
          id: `large-${{index}}`, source: 'large', views: (100 + index * 25) * 20,
          comments: (index % 6) * 20, likes: 0, registeredAt: '2026-08-27T10:00:00Z'
        }});
      }}
      const profile = deals.buildTemperatureProfile(items, now);
      const result = deals.applyTemperatureProfile(items, profile);
      const sourceRows = (source) => result.filter((item) => item.source === source);
      const mean = (rows) => rows.reduce((sum, item) => sum + item.temperature, 0) / rows.length;
      const max = (rows) => Math.max(...rows.map((item) => item.temperature));
      console.log(JSON.stringify({{
        smallMean: mean(sourceRows('small')),
        largeMean: mean(sourceRows('large')),
        smallMax: max(sourceRows('small')),
        largeMax: max(sourceRows('large'))
      }}));
    '''
    out = subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True)
    data = json.loads(out)
    assert abs(data['largeMean'] - data['smallMean']) <= 12
    assert data['largeMax'] >= data['smallMax'] + 5


def test_temperature_uses_only_metrics_with_real_source_coverage():
    script = f'''
      const deals = require({json.dumps(str(ROOT / 'api/_lib/deals.js'))});
      const items = [];
      for (let index = 0; index < 20; index += 1) {{
        items.push({{ source: 'fmkorea', views: 0, comments: 0, likes: index % 11, registeredAt: '2026-08-27T10:00:00Z' }});
        items.push({{ source: 'ruliweb', views: index < 2 ? 9000 : 0, comments: index + 1, likes: 0, registeredAt: '2026-08-27T10:00:00Z' }});
      }}
      const profile = deals.buildTemperatureProfile(items, Date.parse('2026-08-27T12:00:00Z'));
      const fmk = profile.statsBySource.get('fmkorea').metrics;
      const ruli = profile.statsBySource.get('ruliweb').metrics;
      console.log(JSON.stringify({{
        fmkViews: fmk.views.usable, fmkLikes: fmk.likes.usable,
        ruliViews: ruli.views.usable, ruliComments: ruli.comments.usable
      }}));
    '''
    out = subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True)
    assert json.loads(out) == {
        'fmkViews': False,
        'fmkLikes': True,
        'ruliViews': False,
        'ruliComments': True,
    }


def test_temperature_outlier_does_not_collapse_ordinary_source_items_to_zero():
    script = f'''
      const deals = require({json.dumps(str(ROOT / 'api/_lib/deals.js'))});
      const now = Date.parse('2026-08-27T12:00:00Z');
      const items = Array.from({{ length: 20 }}, (_, index) => ({{
        id: String(index), source: 'sample', views: index === 19 ? 100000 : 100 + index * 10,
        comments: 0, likes: 0, registeredAt: '2026-08-27T10:00:00Z'
      }}));
      const result = deals.applyTemperatureProfile(items, deals.buildTemperatureProfile(items, now));
      console.log(JSON.stringify(result.map((item) => item.temperature)));
    '''
    out = subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True)
    temperatures = json.loads(out)
    assert 40 <= temperatures[9] <= 60
    assert temperatures[-1] >= 95


def test_user_row_keeps_manual_temperature():
    script = f'''
      const deals = require({json.dumps(str(ROOT / 'api/_lib/deals.js'))});
      const item = deals.normalizeUserRow({{
        id: 7,
        title: 'manual temp',
        price: '1,000원',
        source: 'user',
        manual_temperature: 87,
        views: 0,
        comments: 0
      }});
      console.log(JSON.stringify({{ temperature: item.temperature, manualTemperature: item.manualTemperature }}));
    '''
    out = subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True, encoding='utf-8')
    data = json.loads(out)
    assert data['temperature'] == 87
    assert data['manualTemperature'] == 87
