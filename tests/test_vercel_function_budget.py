import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / 'api'


def production_function_files():
    return sorted(
        p.relative_to(ROOT).as_posix()
        for p in API_DIR.rglob('*.js')
        if '/_lib/' not in f'/{p.relative_to(ROOT).as_posix()}'
    )


class VercelFunctionBudgetTests(unittest.TestCase):
    def test_hobby_plan_serverless_functions_stay_within_limit(self):
        functions = production_function_files()
        self.assertLessEqual(
            len(functions),
            12,
            f'Vercel Hobby allows at most 12 Serverless Functions; found {len(functions)}: {functions}',
        )

    def test_detail_deal_api_is_folded_into_deals_function(self):
        functions = production_function_files()
        self.assertNotIn('api/deals/[id].js', functions)
        self.assertIn('api/deals.js', functions)

        vercel = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))
        self.assertIn(
            {'source': '/api/deals/:id', 'destination': '/api/deals?id=:id'},
            vercel.get('rewrites', []),
        )


if __name__ == '__main__':
    unittest.main()
