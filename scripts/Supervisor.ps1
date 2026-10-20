$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskStopFile = Join-Path $taskRoot 'data\stop-supervisor'
$taskMutex = New-Object System.Threading.Mutex($false, 'Local\ATLAS-PaperFund-Supervisor')
if (!$taskMutex.WaitOne(0)) { exit }
try {
  if (Test-Path -LiteralPath $taskStopFile) { Remove-Item -LiteralPath $taskStopFile }
  $taskSelf = Get-Process -Id $PID
  @{pid=$PID;started=$taskSelf.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRoot 'data\supervisor.json')
  $taskApi = $null
  $taskWorker = $null
  $taskIdentity = @{}
  while (!(Test-Path -LiteralPath $taskStopFile)) {
    if (!$taskApi -or $taskApi.HasExited) {
      $taskApi = Start-Process -FilePath $taskPython -ArgumentList '-m uvicorn backend.api:app --host 127.0.0.1 --port 8765 --no-access-log' -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskRoot 'logs\api.log') -RedirectStandardError (Join-Path $taskRoot 'logs\api-error.log')
      $taskIdentity.api = @{pid=$taskApi.Id;started=$taskApi.StartTime.ToUniversalTime().ToString('o')}
    }
    $taskBerlin = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'W. Europe Standard Time')
    $taskWorkerMode = & $taskPython (Join-Path $PSScriptRoot 'supervisor_state.py')
    if ($taskWorkerMode -eq 'enabled' -and $taskBerlin.TimeOfDay -ge [TimeSpan]::FromHours(7.5) -and $taskBerlin.TimeOfDay -lt [TimeSpan]::FromHours(19)) {
      if (!$taskWorker -or $taskWorker.HasExited) {
        $taskWorker = Start-Process -FilePath $taskPython -ArgumentList '-m backend.worker' -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskRoot 'logs\worker.log') -RedirectStandardError (Join-Path $taskRoot 'logs\worker-error.log')
        $taskIdentity.worker = @{pid=$taskWorker.Id;started=$taskWorker.StartTime.ToUniversalTime().ToString('o')}
      }
    }
    $taskIdentity | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $taskRoot 'data\processes.json')
    Start-Sleep -Seconds 10
    if ($taskApi) { $taskApi.Refresh() }
    if ($taskWorker) { $taskWorker.Refresh() }
  }
} finally {
  $taskMutex.ReleaseMutex()
  $taskMutex.Dispose()
}
