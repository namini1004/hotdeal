import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "scripts" / "register_hotdeal_quasar_task_windows.ps1"


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Windows task registration")
class QuasarWindowsTaskTests(unittest.TestCase):
    def test_registration_wires_dedicated_runner_and_half_hour_schedule(self):
        for existing in (False, True):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory(prefix="quasar task ") as tmp:
                repo = Path(tmp)
                (repo / "scripts").mkdir()
                (repo / "scripts" / "run_hotdeal_quasar_ingest_windows.ps1").write_text("# stub", encoding="utf-8")
                (repo / "scripts" / "resolve_hotdeal_python.ps1").write_text(
                    "function Resolve-HotdealPython { param($RepoPath, $BootstrapPythonPath) Join-Path $RepoPath 'python.exe' }",
                    encoding="utf-8")
                for name in ("supabase_url.txt", "supabase_service_role_key.txt"):
                    (repo / name).write_text("test", encoding="utf-8")
                mock_existing = "[pscustomobject]@{ State='Ready'; Triggers=@([pscustomobject]@{ Repetition=[pscustomobject]@{Interval='PT30M'}; StartBoundary='2026-08-17T10:05:00' }) }" if existing else "$null"
                script = r'''
$ErrorActionPreference = 'Stop'
function New-ScheduledTaskAction { param($Execute,$Argument,$WorkingDirectory) [pscustomobject]@{Execute=$Execute;Argument=$Argument;WorkingDirectory=$WorkingDirectory} }
function Get-ScheduledTask { param($TaskName,$ErrorAction) EXISTING }
function New-ScheduledTaskTrigger { param([switch]$Once,$At,$RepetitionInterval) [pscustomobject]@{IntervalMinutes=$RepetitionInterval.TotalMinutes} }
function New-ScheduledTaskSettingsSet { param([switch]$StartWhenAvailable,[switch]$AllowStartIfOnBatteries,[switch]$DontStopIfGoingOnBatteries,$MultipleInstances,$ExecutionTimeLimit) [pscustomobject]@{MultipleInstances=$MultipleInstances;LimitMinutes=$ExecutionTimeLimit.TotalMinutes} }
function New-ScheduledTaskPrincipal { param($UserId,$LogonType,$RunLevel) [pscustomobject]@{LogonType=$LogonType;RunLevel=$RunLevel} }
function Register-ScheduledTask { param($TaskName,$Action,$Trigger,$Settings,$Principal,$Description,[switch]$Force) $global:Registration=[pscustomobject]@{TaskName=$TaskName;Action=$Action;Triggers=$Trigger;Settings=$Settings;Force=[bool]$Force} }
function Get-ScheduledTaskInfo { param($TaskName) [pscustomobject]@{TaskName=$TaskName;LastRunTime=$null;LastTaskResult=0;NextRunTime=$null} }
function Start-ScheduledTask { throw 'Registration must not start a collection unless RunNow was requested' }
& 'REGISTER' -RepoPath 'REPO' | Out-Null
$global:Registration | ConvertTo-Json -Depth 8 -Compress
'''.replace("EXISTING", mock_existing).replace("REGISTER", str(REGISTER).replace("'", "''")).replace("REPO", str(repo).replace("'", "''"))
                output = subprocess.check_output(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script], text=True)
                result = json.loads(output)
                self.assertEqual(result["TaskName"], "HotdealQuasarIngest30m")
                self.assertEqual(result["Action"]["WorkingDirectory"], str(repo))
                self.assertIn('run_hotdeal_quasar_ingest_windows.ps1"', result["Action"]["Argument"])
                self.assertNotIn("refresh_hotdeals_windows.ps1", result["Action"]["Argument"])
                for option in ("-PythonPath", "-SupabaseUrlFile", "-SupabaseServiceRoleKeyFile", "-PushIngestSecretFile", "-WindowStyle Hidden"):
                    self.assertIn(option, result["Action"]["Argument"])
                self.assertTrue(result["Force"])
                self.assertEqual(result["Settings"]["MultipleInstances"], "IgnoreNew")
                self.assertEqual(result["Settings"]["LimitMinutes"], 20)
                if existing:
                    self.assertEqual(result["Triggers"][0]["StartBoundary"], "2026-08-17T10:05:00")
                else:
                    self.assertEqual(result["Triggers"][0]["IntervalMinutes"], 30)


if __name__ == "__main__":
    unittest.main()
