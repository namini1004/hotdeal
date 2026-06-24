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
          ['2026-06-08T11:56:01', '3분 전'],
          ['2026-06-08T11:55:00', '5분 전'],
          ['2026-06-08T11:15:00', '45분 전'],
          ['2026-06-08T09:00:00', '3시간 전'],
          ['2026-06-07T23:30:00', '12시간 전'],
          ['2026-06-06T23:30:00', '1일 전'],
          ['2026-06-05T12:00:00', '3일 전'],
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


def test_time_format_uses_elapsed_minutes_hours_and_days():
    for actual, expected in run_time_format_cases():
        assert actual == expected


def test_time_format_parses_source_date_variants():
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const context = {{ window: {{}} }};
        vm.createContext(context);
        vm.runInContext(fs.readFileSync({json.dumps(str(ROOT / 'assets' / 'time-format.js'))}, 'utf8'), context);
        const parseMs = context.window.TimeFormat.parseMs;
        console.log(JSON.stringify([
          parseMs('2026.06.08 11:55') > 0,
          parseMs('2026-06-08') > 0,
          parseMs('06-08 11:55') > 0,
          parseMs('5분 전') > 0,
          parseMs('2시간 전') > 0,
        ]));
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    assert json.loads(completed.stdout) == [True, True, True, True, True]


def test_home_list_uses_relative_time_without_raw_clock_fallback():
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "function displayRelativeTime(item)" in html
    assert "const timeText = displayRelativeTime(item);" in html
    assert "item.registeredAt || item.date || item.time" in html
    assert "replace(/^20\\d{2}-(\\d{2}-\\d{2})$/, '$1')" in html
