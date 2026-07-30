import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_feed_page_uses_range_query_and_global_lightweight_temperature_profile():
    module_path = json.dumps(str(ROOT / "api" / "_lib" / "deals.js"))
    script = f"""
      process.env.SUPABASE_URL = 'https://example.supabase.co';
      process.env.SUPABASE_SERVICE_ROLE_KEY = 'test-key';
      const requests = [];
      const pageRows = Array.from({{ length: 101 }}, (_, index) => ({{
        id: `id-${{index}}`,
        title: `deal-${{index}}`,
        source: index % 2 ? 'ppomppu' : 'quasar',
        source_link: `https://example.com/deal/${{index}}`,
        source_post_id: String(index),
        registered_at: new Date(Date.now() - index * 60000).toISOString(),
        updated_at: new Date().toISOString(),
        views: 100 + index,
        comments: index % 5,
        likes: index % 7,
        dislikes: 0,
        comment_signal_score: 0,
        negative_comment_signals: 0
      }}));
      const scoreRows = pageRows.concat(Array.from({{ length: 40 }}, (_, index) => ({{
        source: index % 2 ? 'ppomppu' : 'quasar',
        registered_at: new Date(Date.now() - (index + 101) * 60000).toISOString(),
        views: 20 + index,
        comments: index % 3,
        likes: 0,
        dislikes: 0,
        comment_signal_score: 0
      }})));
      global.fetch = async (url) => {{
        requests.push(String(url));
        const body = String(url).includes('select=source,views')
          ? scoreRows
          : pageRows;
        return new Response(JSON.stringify(body), {{
          status: 200,
          headers: {{ 'Content-Type': 'application/json' }}
        }});
      }};
      const deals = require({module_path});
      deals.readFeedPage({{ limit: 100, offset: 100 }}).then((page) => {{
        console.log(JSON.stringify({{
          count: page.items.length,
          hasMore: page.hasMore,
          nextOffset: page.nextOffset,
          requests,
          temperatures: page.items.map((item) => item.temperature)
        }}));
      }});
    """
    output = subprocess.check_output(["node", "-e", script], cwd=ROOT, text=True)
    data = json.loads(output)

    assert data["count"] == 100
    assert data["hasMore"] is True
    assert data["nextOffset"] == 200
    assert len(data["requests"]) == 2
    assert any("limit=101&offset=100" in request for request in data["requests"])
    assert any("select=source,views" in request for request in data["requests"])
    assert all(0 <= value <= 100 for value in data["temperatures"])
