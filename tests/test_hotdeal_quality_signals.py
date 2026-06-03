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
