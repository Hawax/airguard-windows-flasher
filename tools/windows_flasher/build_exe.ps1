$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' not found. Install Python 3.11+ from https://www.python.org/downloads/windows/ and tick 'Add python.exe to PATH'."
}

py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt

# Optional at runtime: override firmware URL by setting AIRGUARD_BASE_URL before launching the exe.

.\.venv\Scripts\pyinstaller.exe `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name AirGuardFlasher `
    --collect-all esptool `
    --collect-all serial `
    airguard_flasher.py

Write-Host ""
Write-Host "OK: dist\AirGuardFlasher.exe" -ForegroundColor Green
