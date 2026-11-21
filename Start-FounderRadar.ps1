param([switch]$UsePortablePython, [switch]$LiveAI, [switch]$ExportResults, [string]$Python)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Get-PortablePython {
    $version = '3.14.7'
    $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    switch ($architecture) {
        'AMD64' {
            $package = 'python'
            $expectedHash = '46a4da5529a92d18ff894911f6e6033a8253198d705b8161bf28c9123c87d46b'
        }
        'ARM64' {
            $package = 'pythonarm64'
            $expectedHash = '9eddba7ee2f7ba6c5a1ed1699bd3a62c2e523bad81071d0dbbc8e803bd6c3410'
        }
        default { throw 'Die automatische Einrichtung benoetigt 64-Bit-Windows. Alternativ Python 3.11+ bereitstellen.' }
    }
    $runtime = Join-Path $PSScriptRoot ".fr-runtime\$package-$version"
    $python = Join-Path $runtime 'tools\python.exe'
    $verified = Join-Path $runtime 'package.sha256'
    if ((Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $verified) -and
        (Get-Content -LiteralPath $verified -Raw).Trim() -eq $expectedHash) {
        return $python
    }
    Write-Host 'FounderRadar: portable Python-Laufzeit vorbereiten ...'
    New-Item -Path $runtime -ItemType Directory -Force | Out-Null
    $archive = Join-Path $PSScriptRoot "runtime-packages\$package.$version.zip"
    $bundled = Test-Path -LiteralPath $archive
    if (-not $bundled) {
        $archive = Join-Path $runtime 'python.zip'
        $url = "https://api.nuget.org/v3-flatcontainer/$package/$version/$package.$version.nupkg"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive -TimeoutSec 90
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) {
        throw 'Python-Download konnte nicht verifiziert werden.'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $runtime -Force
    Set-Content -LiteralPath $verified -Value $expectedHash
    if (-not $bundled) { Remove-Item -LiteralPath $archive }
    return $python
}

$venvPython = if ($Python) { (Resolve-Path -LiteralPath $Python).Path } else {
    Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
}
if (-not $Python -and -not (Test-Path -LiteralPath $venvPython)) {
    $basePython = $null
    if (-not $UsePortablePython) {
        $localPython = Join-Path $env:LOCALAPPDATA 'Python\bin\python.exe'
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        $possible = @($localPython, $pythonCommand.Source) | Where-Object { $_ -and $_ -notlike '*\WindowsApps\python.exe' }
        foreach ($candidate in $possible) {
            if (-not (Test-Path -LiteralPath $candidate)) { continue }
            & $candidate -c 'import sys; raise SystemExit(int(sys.version_info < (3, 11)))'
            if ($LASTEXITCODE -eq 0) { $basePython = $candidate; break }
        }
    }
    if (-not $basePython) { $basePython = Get-PortablePython }
    Write-Host 'FounderRadar: lokale Python-Umgebung einrichten ...'
    & $basePython -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python-Umgebung konnte nicht erstellt werden.' }
}
$requirements = Join-Path $PSScriptRoot 'requirements-demo.txt'
$marker = Join-Path $PSScriptRoot '.venv\founderradar-dependencies.sha256'
$digest = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
$installed = if (Test-Path -LiteralPath $marker) { (Get-Content -LiteralPath $marker -Raw).Trim() } else { '' }
if (-not $Python -and $installed -ne $digest) {
    Write-Host 'FounderRadar: getestete Pakete installieren (nur beim ersten Start oder Update) ...'
    & $venvPython -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'Installation fehlgeschlagen. Internetverbindung prüfen und erneut starten.' }
    Set-Content -LiteralPath $marker -Value $digest
}
if ($ExportResults) {
    & $venvPython -m mvp.export_jury (Join-Path $PSScriptRoot 'Ergebnisse')
    if ($LASTEXITCODE -ne 0) { throw 'Ergebnisse konnten nicht exportiert werden.' }
    Start-Process -FilePath (Join-Path $PSScriptRoot 'Ergebnisse\ERGEBNISSE.html')
    exit 0
}

if ($LiveAI) {
    $secret = Read-Host 'OpenAI-Projektschluessel hier einfuegen (sk-...)' -AsSecureString
    $handle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $env:FOUNDERRADAR_LOCAL_AI_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($handle).Trim()
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($handle)
        $secret.Dispose()
    }
    if ($env:FOUNDERRADAR_LOCAL_AI_KEY -notmatch '^sk-[a-zA-Z0-9_-]{16,}$') {
        throw 'Bitte einen gueltigen OpenAI-Projektschluessel eingeben.'
    }
}
try {
    & $venvPython (Join-Path $PSScriptRoot 'launch_founderradar.py')
    if ($LASTEXITCODE -ne 0) { throw 'FounderRadar konnte nicht gestartet werden. Siehe data\mvp\server.log.' }
} finally {
    if ($LiveAI) { Remove-Item Env:FOUNDERRADAR_LOCAL_AI_KEY -ErrorAction SilentlyContinue }
}
