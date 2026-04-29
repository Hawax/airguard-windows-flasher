# AirGuardFlasher.exe

Prosta aplikacja Windows do flashowania AirGuard CO₂ po USB.

## Co robi

- wykrywa porty COM,
- pobiera najnowszy firmware z serwera,
- flashuje ESP32-C3 przez `esptool`,
- przy błędzie próbuje wolniejszej prędkości `115200`,
- pokazuje linki do driverów CP210x/CH340.

## Build `.exe` będąc na Macu

Na macOS nie zbudujesz poprawnie Windows `.exe` przez PyInstaller. Użyj GitHub Actions z `.github/workflows/build-windows-flasher.yml` albo Windows VM. Szczegóły: `BUILD_FROM_MAC.md`.

## Build `.exe` na Windows

1. Zainstaluj Python 3.11+ z <https://www.python.org/downloads/windows/> i zaznacz `Add python.exe to PATH`.
2. W PowerShell:

```powershell
cd tools\windows_flasher
.\build_exe.ps1
```

Gotowy plik:

```text
tools\windows_flasher\dist\AirGuardFlasher.exe
```

Ten plik możesz wysłać użytkownikowi.

## Serwer firmware

Domyślnie appka używa:

```text
http://57.128.218.234/kq8bV4oF9kqouQij4Q5F/air-guard-co2/
```

Na serwerze powinno być przynajmniej:

```text
version.txt
firmware.bin
```

Lepiej: użyj `./full_deploy.sh --upload-ota`, wtedy skrypt wrzuca też `manifest.json`, `bootloader.bin`, `partition-table.bin`, `ota_data_initial.bin`; flasher użyje pełnego flashowania dla pustego ESP32-C3.

Możesz zmienić adres w GUI albo przy budowaniu/uruchamianiu przez zmienną:

```powershell
$env:AIRGUARD_BASE_URL="https://twoja-domena.pl/kq8bV4oF9kqouQij4Q5F/air-guard-co2/"
.\build_exe.ps1
```

## Driver dla użytkownika

Jeśli nie widać portu COM, użytkownik musi zainstalować driver zależnie od konwertera USB-UART:

- CP210x: <https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers>
- CH340: <https://www.wch-ic.com/downloads/CH341SER_EXE.html>

Po instalacji: odłączyć i podłączyć kabel USB ponownie.
