import json
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_time_format_cases():
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const context = {{ window: {{}} }};
        vm.createContext(context);
        vm.runInContext(fs.readFileSync({json.dumps(str(ROOT / 'assets' / 'time-format.js'))}, 'utf8'), context);
        const fmt = context.window.TimeFormat.toRelativeKorean;
        const now = '2026-06-08T12:00:00';
        const cases = [
          ['2026-06-08T11:56:01', '방금 전'],
          ['2026-06-08T11:55:00', '5분전'],
          ['2026-06-08T11:15:00', '45분전'],
          ['2026-06-08T09:00:00', '3시간전'],
          ['2026-06-07T23:30:00', '어제'],
          ['2026-06-06T23:30:00', '그저께'],
          ['2026-06-05T12:00:00', '3일전'],
        ];
        console.log(JSON.stringify(cases.map(([value, expected]) => [fmt(value, {{ now }}), expected])));
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def test_time_format_uses_recent_minutes_hours_and_calendar_days():
    for actual, expected in run_time_format_cases():
        assert actual == expected
