import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_node(script: str):
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        encoding='utf-8',
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


class ShareSeoTests(unittest.TestCase):
    def test_share_meta_builds_safe_title_description_image_and_urls(self):
        script = r"""
        const { buildShareMeta } = require('./api/_lib/share-meta');
        const meta = buildShareMeta({
          id: 'deal-1',
          title: '<b>에어팟 프로</b> 초특가',
          price: '229,000원',
          category: '디지털',
          source: 'ppomppu',
          img: 'https://example.com/a.webp',
          desc: '좋은 가격입니다.\n두 줄 설명'
        }, 'https://gaji.run');
        console.log(JSON.stringify(meta));
        """
        meta = json.loads(run_node(script))

        self.assertEqual(meta['title'], '[가지] 에어팟 프로 초특가 229,000원')
        self.assertNotIn('<', meta['title'])
        self.assertTrue(meta['description'].startswith('디지털 · 뽐딜 · 229,000원'))
        self.assertEqual(meta['image'], 'https://example.com/a.webp')
        self.assertEqual(meta['canonicalUrl'], 'https://gaji.run/d/deal-1')
        self.assertEqual(meta['detailUrl'], 'https://gaji.run/indexdetail.html?id=deal-1')

    def test_share_html_contains_og_twitter_canonical_and_human_redirect(self):
        script = r"""
        const { buildShareMeta, renderShareHtml } = require('./api/_lib/share-meta');
        const meta = buildShareMeta({ id: 'abc', title: '테스트딜', price: '무료', img: '' }, 'https://gaji.run');
        console.log(renderShareHtml(meta));
        """
        html = run_node(script)

        self.assertIn('<meta property="og:title" content="[가지] 테스트딜 무료" />', html)
        self.assertIn('<meta property="og:type" content="product" />', html)
        self.assertIn('<meta name="twitter:card" content="summary_large_image" />', html)
        self.assertIn('<link rel="canonical" href="https://gaji.run/d/abc" />', html)
        self.assertIn('window.location.replace("https://gaji.run/indexdetail.html?id=abc")', html)
        self.assertIn('0;url=https://gaji.run/indexdetail.html?id=abc', html)

    def test_robots_sitemap_and_detail_rewrite_are_present(self):
        robots = (ROOT / 'robots.txt').read_text(encoding='utf-8')
        sitemap = (ROOT / 'sitemap.xml').read_text(encoding='utf-8')
        vercel = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))

        self.assertIn('Sitemap: https://gaji.run/sitemap.xml', robots)
        self.assertIn('<loc>https://gaji.run/</loc>', sitemap)
        self.assertIn('<loc>https://gaji.run/index.html</loc>', sitemap)

        rewrites = vercel.get('rewrites', [])
        self.assertIn({'source': '/d/:id', 'destination': '/api/share?id=:id'}, rewrites)

        redirects = vercel.get('redirects', [])
        self.assertIn({
            'source': '/:path*',
            'has': [{'type': 'host', 'value': 'www.gaji.run'}],
            'destination': 'https://gaji.run/:path*',
            'permanent': True,
        }, redirects)


if __name__ == '__main__':
    unittest.main()
