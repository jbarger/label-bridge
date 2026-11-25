# Builds the Windows installer: dist\LabelBridge-Setup-<version>.exe
#   powershell -ExecutionPolicy Bypass -File .\windows\build.ps1
# Needs Python 3.10+ and Inno Setup 6 (winget install JRSoftware.InnoSetup).
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$work = Join-Path $here 'build'
Push-Location $here
try {
    function Invoke-Tool { param([string]$exe) & $exe @args; if ($LASTEXITCODE) { throw "$exe failed ($LASTEXITCODE)" } }

    $version = (Select-String -Path labelprinter.py -Pattern '^VERSION = "(.+)"').Matches[0].Groups[1].Value
    Write-Host "Label Bridge $version"

    Invoke-Tool python -m pip install -q -r requirements.txt pyinstaller
    New-Item -ItemType Directory -Force $work | Out-Null
    $ico = Join-Path $work 'labelbridge.ico'
    Invoke-Tool python "$root\android\make_icon.py" --ico $ico

    Invoke-Tool python -m PyInstaller --noconfirm --clean --windowed --name LabelBridge `
        --icon $ico --add-data "$ico;." `
        --hidden-import pystray._win32 --collect-submodules zeroconf `
        --distpath "$work\dist" --workpath "$work\work" --specpath $work `
        (Join-Path $here 'labelprinter.py')

    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
              "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw 'Inno Setup 6 not found: winget install JRSoftware.InnoSetup' }
    Invoke-Tool $iscc /Q "/DAppVer=$version" installer.iss
    Get-Item "$root\dist\LabelBridge-Setup-$version.exe" | ForEach-Object { Write-Host "Built $($_.FullName) ($([math]::Round($_.Length / 1MB, 1)) MB)" }
} finally { Pop-Location }
