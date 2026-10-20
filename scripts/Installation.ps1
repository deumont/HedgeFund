$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (!(Test-Path -LiteralPath $taskPython)) {
  winget install --id Python.Python.3.12 --exact --scope user --silent --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity
}
$taskNode = Join-Path $env:ProgramFiles 'nodejs\npm.cmd'
if (!(Test-Path -LiteralPath $taskNode)) {
  winget install --id OpenJS.NodeJS.LTS --exact --silent --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity
}
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe')) { & $taskPython -m venv .venv }
& '.\.venv\Scripts\python.exe' -m pip install -e '.[test]'
if ($LASTEXITCODE -ne 0) { throw 'Python-Installation fehlgeschlagen' }
$env:Path = (Join-Path $env:ProgramFiles 'nodejs') + ';' + $env:Path
Push-Location -LiteralPath (Join-Path $taskRoot 'frontend')
try {
  & $taskNode ci --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw 'Frontend-Abhängigkeiten fehlen' }
  & $taskNode run build
  if ($LASTEXITCODE -ne 0) { throw 'Frontend-Build fehlgeschlagen' }
} finally { Pop-Location }
& '.\.venv\Scripts\python.exe' scripts\setup_local.py
& '.\.venv\Scripts\python.exe' -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests fehlgeschlagen' }
Write-Output 'Installation geprüft. Start.cmd öffnet ATLAS.'
