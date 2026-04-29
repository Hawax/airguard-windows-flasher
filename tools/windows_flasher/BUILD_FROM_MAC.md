# Jak zbudować Windows `.exe` będąc na Macu

PyInstaller nie cross-kompiluje Windows `.exe` z macOS. Najprostsza droga: GitHub Actions / Windows runner.

## Opcja A — GitHub Actions

1. Wypchnij repo do GitHuba.
2. Wejdź w zakładkę **Actions**.
3. Wybierz workflow **Build Windows Flasher**.
4. Kliknij **Run workflow**.
5. Po zakończeniu pobierz artifact:

```text
AirGuardFlasher-windows-exe
```

W środku będzie:

```text
AirGuardFlasher.exe
```

To jest plik do wysłania użytkownikowi.

## Opcja B — dowolny Windows / Windows VM

Na Windowsie:

```powershell
cd tools\windows_flasher
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Gotowy plik:

```text
tools\windows_flasher\dist\AirGuardFlasher.exe
```

## Ważne

Użytkownik Windows nie musi instalować Pythona, `esptool` ani `pyserial` — są spakowane do `.exe`.
Sterowniki USB CP210x/CH340 nadal instaluje osobno z linków w aplikacji, jeśli Windows nie pokazuje portu COM.
