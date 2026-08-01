$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$launcher = Join-Path $projectRoot "Start Jarvis.bat"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Jarvis.lnk"
$exePath = Join-Path $projectRoot "dist\Jarvis.exe"

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Launcher not found: $launcher"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = "Start Jarvis AI assistant"

if (Test-Path -LiteralPath $exePath) {
    $shortcut.IconLocation = "$exePath,0"
} else {
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,14"
}

$shortcut.Save()
Write-Host "Desktop icon created: $shortcutPath"
