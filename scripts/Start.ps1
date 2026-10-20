param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $taskPython)) { throw 'Python-Umgebung fehlt. Zuerst Installation.ps1 ausführen.' }
& $taskPython (Join-Path $PSScriptRoot 'setup_local.py')
$taskSupervisorFile = Join-Path $taskRoot 'data\supervisor.json'
$taskAlreadyRunning = $false
if (Test-Path -LiteralPath $taskSupervisorFile) {
  $taskInfo = Get-Content -LiteralPath $taskSupervisorFile -Raw | ConvertFrom-Json
  $taskProc = Get-Process -Id $taskInfo.pid -ErrorAction SilentlyContinue
  if ($taskProc -and [Math]::Abs(($taskProc.StartTime.ToUniversalTime() - [DateTime]::Parse($taskInfo.started).ToUniversalTime()).TotalSeconds) -lt 2) { $taskAlreadyRunning = $true }
}
if (!$taskAlreadyRunning) {
  $taskArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'Supervisor.ps1') + '"'
  Start-Process -FilePath 'powershell.exe' -ArgumentList $taskArgs -WorkingDirectory $taskRoot -WindowStyle Hidden
}
for ($taskAttempt = 0; $taskAttempt -lt 30; $taskAttempt++) {
  try { $taskHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 2; if ($taskHealth.status -eq 'ok') { break } } catch { Start-Sleep -Seconds 1 }
}
if (!$taskHealth -or $taskHealth.status -ne 'ok') { throw 'Start fehlgeschlagen; logs\api-error.log prüfen.' }
if (!$NoBrowser) { Start-Process 'http://127.0.0.1:8765' }
Write-Output 'ATLAS läuft im Hintergrund. Zugang: local-access.txt. Beenden mit Stopp.cmd.'
