$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
New-Item -ItemType File -Force -Path (Join-Path $taskRoot 'data\stop-supervisor') | Out-Null
& $taskPython (Join-Path $PSScriptRoot 'shutdown.py')
Start-Sleep -Seconds 2
$taskProcessesFile = Join-Path $taskRoot 'data\processes.json'
if (Test-Path -LiteralPath $taskProcessesFile) {
  $taskProcesses = Get-Content -LiteralPath $taskProcessesFile -Raw | ConvertFrom-Json
  foreach ($taskRole in @('worker','api')) {
    $taskIdentity = $taskProcesses.$taskRole
    if (!$taskIdentity) { continue }
    $taskProc = Get-Process -Id $taskIdentity.pid -ErrorAction SilentlyContinue
    if ($taskProc -and [Math]::Abs(($taskProc.StartTime.ToUniversalTime() - [DateTime]::Parse($taskIdentity.started).ToUniversalTime()).TotalSeconds) -lt 2) {
      if ($taskRole -eq 'worker') {
        Write-Output 'Worker reagiert noch nicht; vor erzwungenem Abbruch aktuelle API-Anfrage abwarten. Keine fremden Prozesse werden beendet.'
      } else { Stop-Process -Id $taskProc.Id }
    }
  }
}
if (Test-Path -LiteralPath (Join-Path $taskRoot 'data\supervisor.json')) {
  $taskSupervisor = Get-Content -LiteralPath (Join-Path $taskRoot 'data\supervisor.json') -Raw | ConvertFrom-Json
  for ($taskAttempt = 0; $taskAttempt -lt 15; $taskAttempt++) {
    $taskProc = Get-Process -Id $taskSupervisor.pid -ErrorAction SilentlyContinue
    if (!$taskProc -or [Math]::Abs(($taskProc.StartTime.ToUniversalTime() - [DateTime]::Parse($taskSupervisor.started).ToUniversalTime()).TotalSeconds) -ge 2) { break }
    Start-Sleep -Seconds 1
  }
}
Write-Output 'ATLAS-Stopp angefordert; Zustand und Backup sind lokal gespeichert.'
