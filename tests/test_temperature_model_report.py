import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_temperature_report_contains_all_sources_and_tuning_diagnostics():
    module_path = json.dumps(str(ROOT / "scripts" / "report_temperature_model.js"))
    rows = []
    for index in range(20):
        rows.extend(
            [
                {
                    "source": "ppomppu",
                    "registered_at": "2026-08-27T08:00:00Z",
                    "views": 100 + index * 20,
                    "comments": index % 4,
                },
                {
                    "source": "quasar",
                    "registered_at": "2026-08-27T08:00:00Z",
                    "views": 2000 + index * 200,
                    "comments": 5 + index % 8,
                },
                {
                    "source": "fmkorea",
                    "registered_at": "2026-08-27T08:00:00Z",
                    "likes": index % 10,
                },
                {
                    "source": "ruliweb",
                    "registered_at": "2026-08-27T08:00:00Z",
                    "comments": 2 + index,
                },
            ]
        )
    script = f"""
      const report = require({module_path});
      const rows = {json.dumps(rows)};
      process.stdout.write(report.renderMarkdown(rows, [], new Date('2026-08-27T10:00:00Z')));
    """
    output = subprocess.check_output(["node", "-e", script], cwd=ROOT, text=True, encoding="utf-8")
    assert "# 가지온도 모델 일일 리포트" in output
    assert "| 뽐뿌 |" in output
    assert "| 퀘이사존 |" in output
    assert "| 펨코 |" in output
    assert "| 루리웹 |" in output
    assert "사이트 상대 점수 85% + 전체 절대 반응 15%" in output
    assert "상위 20개 구성" in output
    assert "100도 비율" in output
