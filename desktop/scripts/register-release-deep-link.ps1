$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopDir = Split-Path -Parent $scriptDir
$releaseExe = Join-Path $desktopDir "src-tauri\target\release\lingosync-desktop.exe"

if (!(Test-Path -LiteralPath $releaseExe)) {
  throw "Release client not found: $releaseExe. Run 'npm run client:build' first."
}

$schemeRoot = "HKCU:\Software\Classes\lingosync"
$commandKey = Join-Path $schemeRoot "shell\open\command"
$command = "`"$releaseExe`" `"%1`""

New-Item -Path $schemeRoot -Force | Out-Null
New-Item -Path $commandKey -Force | Out-Null
Set-Item -Path $schemeRoot -Value "URL:LingoSync Protocol"
Set-ItemProperty -Path $schemeRoot -Name "URL Protocol" -Value ""
Set-Item -Path $commandKey -Value $command

Write-Host "Registered lingosync:// -> $releaseExe"
