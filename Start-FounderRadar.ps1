$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$localPython = Join-Path $env:LOCALAPPDATA 'Python\bin\python.exe'
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
$basePython = if (Test-Path -LiteralPath $localPython) { $localPython } elseif ($pythonCommand) { $pythonCommand.Source } else { $null }
if (-not $basePython) { throw 'Python wurde nicht gefunden. Bitte Python 3.11 oder neuer installieren und erneut starten.' }
& $basePython -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11 oder neuer erforderlich"'
if ($LASTEXITCODE -ne 0) { throw 'Python konnte nicht gestartet werden.' }
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'FounderRadar: lokale Python-Umgebung einrichten ...'
    & $basePython -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python-Umgebung konnte nicht erstellt werden.' }
}
$requirements = Join-Path $PSScriptRoot 'requirements-demo.txt'
$marker = Join-Path $PSScriptRoot '.venv\founderradar-dependencies.sha256'
$digest = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
$installed = if (Test-Path -LiteralPath $marker) { (Get-Content -LiteralPath $marker -Raw).Trim() } else { '' }
if ($installed -ne $digest) {
    Write-Host 'FounderRadar: getestete Pakete installieren (nur beim ersten Start oder Update) ...'
    & $venvPython -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'Installation fehlgeschlagen. Internetverbindung prüfen und erneut starten.' }
    Set-Content -LiteralPath $marker -Value $digest
}
& $venvPython (Join-Path $PSScriptRoot 'launch_founderradar.py')
if ($LASTEXITCODE -ne 0) { throw 'FounderRadar konnte nicht gestartet werden. Siehe data\mvp\server.log.' }
