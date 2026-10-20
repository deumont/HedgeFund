# Opt-in local Windows tasks: no password storage, only runs while user is logged on.
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $PSScriptRoot 'Start.ps1') + '" -NoBrowser') -WorkingDirectory $taskRoot
$taskTriggers = @((New-ScheduledTaskTrigger -Daily -At '07:30'), (New-ScheduledTaskTrigger -AtLogOn -User $taskUser))
$taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
try {
  Register-ScheduledTask -TaskName 'ATLAS Paper Fund' -Action $taskAction -Trigger $taskTriggers -Settings $taskSettings -Principal $taskPrincipal -Description 'Lokales Paper-Forschungssystem; keine Echtgeldorders' -Force | Out-Null
  Write-Output 'Aufgabenplanung: bei Anmeldung und täglich 07:30 eingerichtet.'
} catch {
  # Windows can deny task registration even for a local administrator's filtered token.
  # A per-user Startup shortcut needs no elevation; supervisor waits for Berlin 07:30.
  $taskStartup = [Environment]::GetFolderPath('Startup')
  $taskShell = New-Object -ComObject WScript.Shell
  $taskLink = $taskShell.CreateShortcut((Join-Path $taskStartup 'ATLAS Paper Fund.lnk'))
  $taskLink.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $taskLink.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $PSScriptRoot 'Start.ps1') + '" -NoBrowser'
  $taskLink.WorkingDirectory = $taskRoot
  $taskLink.WindowStyle = 7
  $taskLink.Description = 'ATLAS: lokales Paper-System; Worker ab 07:30 Berlin'
  $taskLink.Save()
  Write-Output 'Aufgabenplanung verweigert. Benutzer-Autostart bei Anmeldung eingerichtet; Supervisor startet den Worker ab 07:30 Berlin.'
}
