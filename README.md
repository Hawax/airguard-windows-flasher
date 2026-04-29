# AirGuard Windows Flasher

Windows `.exe` flasher dla AirGuard CO₂ / ESP32-C3.

## Dla użytkownika końcowego

Wyślij mu plik:

```text
AirGuardFlasher.exe
```

Aplikacja:

- wykrywa porty COM,
- pobiera najnowszy firmware z serwera,
- flashuje ESP32-C3 przez `esptool`,
- przy błędzie próbuje wolniej `115200`,
- pokazuje instrukcję BOOT/reset,
- ma linki do sterowników CP210x/CH340.

## Build `.exe` przez GitHub Actions

1. Wejdź w **Actions**.
2. Odpal workflow **Build Windows Flasher**.
3. Pobierz artifact `AirGuardFlasher-windows-exe`.
4. W środku jest `AirGuardFlasher.exe`.

## Build lokalnie na Windows

```powershell
cd tools\windows_flasher
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Gotowy exe:

```text
tools\windows_flasher\dist\AirGuardFlasher.exe
```

## Firmware URL

Domyślnie flasher używa:

```text
http://57.128.218.234/kq8bV4oF9kqouQij4Q5F/air-guard-co2/
```

Na serwerze najlepiej mieć pliki generowane przez `full_deploy.sh --upload-ota` z firmware repo:

- `manifest.json`
- `version.txt`
- `firmware.bin`
- `bootloader.bin`
- `partition-table.bin`
- `ota_data_initial.bin`
