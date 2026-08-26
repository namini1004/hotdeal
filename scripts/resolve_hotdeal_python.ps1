function Resolve-HotdealPython {
    Param(
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,

        [Parameter(Mandatory = $true)]
        [string]$BootstrapPythonPath
    )

    $EnvironmentPath = Join-Path $RepoPath ".tools\hotdeal-python"
    $ManagedPythonPath = Join-Path $EnvironmentPath "Scripts\python.exe"
    $RequirementsPath = Join-Path $RepoPath "scripts\requirements-hotdeal-local.txt"

    if (-not (Test-Path -LiteralPath $RequirementsPath)) {
        throw "Local Python requirements not found: $RequirementsPath"
    }

    if (-not (Test-Path -LiteralPath $ManagedPythonPath)) {
        if (-not (Test-Path -LiteralPath $BootstrapPythonPath)) {
            throw "Bootstrap Python not found: $BootstrapPythonPath"
        }

        New-Item -ItemType Directory -Force -Path (Split-Path $EnvironmentPath -Parent) | Out-Null
        $VenvOutput = & $BootstrapPythonPath -m venv $EnvironmentPath 2>&1
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $ManagedPythonPath)) {
            throw "Failed to create local Python environment: $($VenvOutput | Out-String)"
        }
    }

    & $ManagedPythonPath -c "import PIL, playwright, requests" *> $null
    if ($LASTEXITCODE -ne 0) {
        $InstallOutput = & $ManagedPythonPath -m pip install --disable-pip-version-check -r $RequirementsPath 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install local Python dependencies: $($InstallOutput | Out-String)"
        }
    }

    return $ManagedPythonPath
}
