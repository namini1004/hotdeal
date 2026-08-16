Param(
    [string]$PythonHome = "C:\Users\namin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PythonExe = Join-Path $PythonHome "python.exe"
$PythonScripts = Join-Path $PythonHome "Scripts"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$Segments = @($UserPath -split ";" | Where-Object { $_ -and $_.Trim() })
foreach ($PathToAdd in @($PythonHome, $PythonScripts)) {
    if (-not ($Segments | Where-Object { $_.TrimEnd("\") -ieq $PathToAdd.TrimEnd("\") })) {
        $Segments += $PathToAdd
    }
}
[Environment]::SetEnvironmentVariable("Path", ($Segments -join ";"), "User")
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
[Environment]::SetEnvironmentVariable("PYTHONIOENCODING", "utf-8", "User")

# PowerShell's Windows default is Restricted, which prevents the PATH bootstrap
# below from loading in shells launched by an already-running desktop process.
if ((Get-ExecutionPolicy -Scope CurrentUser) -in @("Undefined", "Restricted")) {
    try {
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force -ErrorAction Stop
    }
    catch {
        # A process-level Bypass can make Set-ExecutionPolicy report an override
        # even though the CurrentUser value was persisted successfully.
        if ((Get-ExecutionPolicy -Scope CurrentUser) -ne "RemoteSigned") {
            throw
        }
    }
}

$StartMarker = "# >>> gaji-python >>>"
$EndMarker = "# <<< gaji-python <<<"
$Pattern = "(?s)" + [regex]::Escape($StartMarker) + ".*?" + [regex]::Escape($EndMarker) + "\s*"
$Block = @"
$StartMarker
`$GajiPythonHome = '$PythonHome'
`$GajiPythonScripts = '$PythonScripts'
if (Test-Path -LiteralPath (Join-Path `$GajiPythonHome 'python.exe')) {
    `$CurrentPathSegments = @(`$env:Path -split ';')
    if (-not (`$CurrentPathSegments | Where-Object { `$_.TrimEnd('\') -ieq `$GajiPythonHome.TrimEnd('\') })) {
        `$env:Path = "`$GajiPythonHome;`$GajiPythonScripts;`$env:Path"
    }
    `$env:PYTHONUTF8 = '1'
    `$env:PYTHONIOENCODING = 'utf-8'
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding(`$false)
}
$EndMarker
"@
$DocumentsPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
$ProfilePaths = @(
    $PROFILE.CurrentUserAllHosts,
    (Join-Path $HOME "Documents\WindowsPowerShell\profile.ps1"),
    (Join-Path $HOME "Documents\PowerShell\profile.ps1"),
    (Join-Path $DocumentsPath "WindowsPowerShell\profile.ps1"),
    (Join-Path $DocumentsPath "PowerShell\profile.ps1")
) | Select-Object -Unique
foreach ($ProfilePath in $ProfilePaths) {
    $ProfileDir = Split-Path -Parent $ProfilePath
    New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
    $Existing = if (Test-Path -LiteralPath $ProfilePath) {
        Get-Content -Raw -LiteralPath $ProfilePath
    }
    else {
        ""
    }
    $Existing = [regex]::Replace($Existing, $Pattern, "").TrimEnd()
    $NewContent = if ($Existing) { "$Existing`r`n`r`n$Block" } else { $Block }
    Set-Content -LiteralPath $ProfilePath -Value $NewContent -Encoding UTF8
}

$env:Path = "$PythonHome;$PythonScripts;$env:Path"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Output "python=$PythonExe"
Write-Output "profiles=$($ProfilePaths -join ';')"
Write-Output "userPath=$([Environment]::GetEnvironmentVariable('Path', 'User'))"
Write-Output "currentUserExecutionPolicy=$(Get-ExecutionPolicy -Scope CurrentUser)"
& $PythonExe --version
