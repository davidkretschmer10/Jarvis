$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

Write-Host "=== Jarvis environment repair ==="
Write-Host "Project: $projectRoot"

function Find-Python {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Python311\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.11-64\python.exe")
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return $py.Source
    }

    return $null
}

$pythonExe = Find-Python
if (-not $pythonExe) {
    throw "Python 3.11 was not found. Install Python 3.11, then run this script again."
}

Write-Host "Python found: $pythonExe"
if ((Split-Path -Leaf $pythonExe) -ieq "py.exe") {
    & $pythonExe -3.11 --version
} else {
    & $pythonExe --version
}

$venvWorks = $false
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -c "import sys; print(sys.executable)" *> $null
    $venvWorks = ($LASTEXITCODE -eq 0)
}

if (-not $venvWorks) {
    Write-Host "Recreating .venv..."
    if (Test-Path -LiteralPath $venvDir) {
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }
    if ((Split-Path -Leaf $pythonExe) -ieq "py.exe") {
        & $pythonExe -3.11 -m venv $venvDir
    } else {
        & $pythonExe -m venv $venvDir
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw ".venv creation failed: $venvPython was not created."
}

Write-Host "Upgrading pip..."
& $venvPython -m pip install --upgrade pip

Write-Host "Installing Jarvis requirements..."
& $venvPython -m pip install -r (Join-Path $projectRoot "requirements.txt")

Write-Host "Checking GUI dependency..."
& $venvPython -c "import PySide6; print('PySide6 OK')"

Write-Host "Environment repair completed."
