"""AirGuard Windows USB flasher.

Build to a single .exe with build_exe.ps1 on Windows.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import queue
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import messagebox, ttk

try:
    from serial.tools import list_ports
except Exception:  # pragma: no cover - shown in GUI
    list_ports = None

APP_NAME = "AirGuard Flasher"
DEFAULT_BASE_URL = "http://57.128.218.234/kq8bV4oF9kqouQij4Q5F/air-guard-co2/"
# If DNS name above is local-only, override while building/running:
#   set AIRGUARD_BASE_URL=https://twoja-domena.pl/.../air-guard-co2/
BASE_URL = os.environ.get("AIRGUARD_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + "/"

DRIVER_LINKS = {
    "CP210x / Silicon Labs": "https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers",
    "CH340 / WCH": "https://www.wch-ic.com/downloads/CH341SER_EXE.html",
    "ESP-IDF USB/JTAG": "https://docs.espressif.com/projects/esp-idf/en/latest/esp32c3/api-guides/jtag-debugging/configure-builtin-jtag.html",
}


@dataclass
class FirmwareFile:
    name: str
    url: str
    offset: str
    path: Path | None = None


@dataclass
class FirmwareManifest:
    version: str
    chip: str
    flash_size: str
    baud: int
    files: list[FirmwareFile]


class QueueWriter(io.TextIOBase):
    def __init__(self, emit: Callable[[str], None]) -> None:
        self.emit = emit

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        if text:
            self.emit(text)
        return len(text)

    def flush(self) -> None:
        return None


class AirGuardFlasher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("820x620")
        self.minsize(720, 520)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_requested = False
        self.manifest: FirmwareManifest | None = None
        self.ports: list[str] = []

        self.port_var = tk.StringVar()
        self.version_var = tk.StringVar(value="nie sprawdzono")
        self.status_var = tk.StringVar(value="Gotowe")
        self.erase_var = tk.BooleanVar(value=False)
        self.baud_var = tk.StringVar(value="460800")

        self._build_ui()
        self.after(100, self._drain_log_queue)
        self.refresh_ports()
        self.check_latest_async()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text="AirGuard CO₂ — USB flasher", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.status_var).pack(side="right")

        cfg = ttk.LabelFrame(root, text="Konfiguracja", padding=10)
        cfg.pack(fill="x", pady=(12, 8))
        cfg.columnconfigure(1, weight=1)

        ttk.Label(cfg, text="Wersja firmware:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(cfg, textvariable=self.version_var, font=("Segoe UI", 10, "bold")).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Button(cfg, text="Sprawdź", command=self.check_latest_async).grid(row=0, column=2, padx=4, pady=4)

        ttk.Label(cfg, text="Port COM:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.port_combo = ttk.Combobox(cfg, textvariable=self.port_var, state="readonly", width=28)
        self.port_combo.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Button(cfg, text="Odśwież porty", command=self.refresh_ports).grid(row=1, column=2, padx=4, pady=4)
        ttk.Button(cfg, text="Menedżer urządzeń", command=self.open_device_manager).grid(row=1, column=3, padx=4, pady=4)

        ttk.Label(cfg, text="Prędkość:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(cfg, textvariable=self.baud_var, values=("460800", "230400", "115200"), width=12, state="readonly").grid(row=2, column=1, sticky="w", pady=4)
        ttk.Checkbutton(cfg, text="Wyczyść flash przed wgrywaniem (dla nowych/problemowych urządzeń)", variable=self.erase_var).grid(row=2, column=2, columnspan=3, sticky="w", pady=4)

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(4, 8))
        self.flash_btn = ttk.Button(actions, text="Pobierz najnowszy firmware i flashuj", command=self.flash_async)
        self.flash_btn.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Tylko pobierz/sprawdź", command=self.check_latest_async).pack(side="left", padx=4)
        ttk.Button(actions, text="Sterowniki USB", command=self.show_drivers).pack(side="left", padx=4)
        ttk.Button(actions, text="Pomoc przy błędzie", command=self.show_boot_help).pack(side="left", padx=4)

        tips = ttk.LabelFrame(root, text="Szybka instrukcja", padding=10)
        tips.pack(fill="x", pady=(0, 8))
        ttk.Label(
            tips,
            text=(
                "1) Podłącz AirGuard przez USB.  2) Kliknij „Odśwież porty”.  "
                "3) Wybierz COM i kliknij flash.  Jeśli portu nie ma — zainstaluj CP210x albo CH340."
            ),
            wraplength=760,
        ).pack(anchor="w")

        log_frame = ttk.LabelFrame(root, text="Log", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=16, wrap="word", font=("Consolas", 9))
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def log(self, text: str) -> None:
        self.log_queue.put(text)

    def log_line(self, text: str = "") -> None:
        self.log(text + "\n")

    def _drain_log_queue(self) -> None:
        try:
            while True:
                text = self.log_queue.get_nowait()
                self.log_text.insert("end", text)
                self.log_text.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    def set_busy(self, busy: bool, status: str) -> None:
        self.status_var.set(status)
        self.flash_btn.configure(state="disabled" if busy else "normal")

    def run_worker(self, target: Callable[[], None], status: str) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME, "Operacja już trwa.")
            return

        def wrapped() -> None:
            self.after(0, lambda: self.set_busy(True, status))
            try:
                target()
            except Exception as exc:
                self.log_line("\nBŁĄD:")
                self.log_line(str(exc))
                self.log_line(traceback.format_exc())
                self.after(0, lambda: messagebox.showerror(APP_NAME, str(exc)))
            finally:
                self.after(0, lambda: self.set_busy(False, "Gotowe"))

        self.worker = threading.Thread(target=wrapped, daemon=True)
        self.worker.start()

    def base_url(self) -> str:
        # Hidden from end users; can still be overridden for testing/builds via AIRGUARD_BASE_URL.
        return BASE_URL

    def refresh_ports(self) -> None:
        self.ports = []
        display: list[str] = []
        if list_ports is None:
            self.log_line("Brak pyserial — zbuduj .exe z requirements.txt.")
            return
        for port in list_ports.comports():
            label = f"{port.device} — {port.description}"
            display.append(label)
            self.ports.append(port.device)
        self.port_combo.configure(values=display)
        if display:
            self.port_combo.current(0)
            self.log_line("Wykryte porty: " + ", ".join(self.ports))
        else:
            self.port_var.set("")
            self.log_line("Nie wykryto portów COM. Sprawdź kabel USB i sterownik CP210x/CH340.")

    def selected_port(self) -> str:
        selected = self.port_var.get()
        if " — " in selected:
            return selected.split(" — ", 1)[0]
        return selected.strip()

    def urlopen_bytes(self, url: str, timeout: int = 25) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "AirGuardFlasher/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()

    def fetch_text(self, url: str) -> str:
        return self.urlopen_bytes(url).decode("utf-8", errors="replace").strip()

    def load_manifest(self) -> FirmwareManifest:
        base = self.base_url()
        manifest_url = urllib.parse.urljoin(base, "manifest.json")
        self.log_line(f"Sprawdzam manifest: {manifest_url}")
        try:
            raw = self.urlopen_bytes(manifest_url)
            data = json.loads(raw.decode("utf-8"))
            version = str(data.get("version") or "unknown")
            chip = str(data.get("chip") or "esp32c3")
            flash_size = str(data.get("flash_size") or "4MB")
            baud = int(data.get("baud") or self.baud_var.get() or 460800)
            files = []
            for item in data.get("files", []):
                name = str(item["name"])
                url = str(item.get("url") or name)
                offset = str(item["offset"])
                files.append(FirmwareFile(name=name, url=urllib.parse.urljoin(base, url), offset=offset))
            if not files:
                raise ValueError("manifest.json nie zawiera listy files")
            return FirmwareManifest(version=version, chip=chip, flash_size=flash_size, baud=baud, files=files)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
            self.log_line(f"Manifest niedostępny ({exc}). Używam fallback: version.txt + firmware.bin.")
            version = self.fetch_text(urllib.parse.urljoin(base, "version.txt"))
            return FirmwareManifest(
                version=version,
                chip="esp32c3",
                flash_size="4MB",
                baud=int(self.baud_var.get() or 460800),
                files=[FirmwareFile("firmware.bin", urllib.parse.urljoin(base, "firmware.bin"), "0x20000")],
            )

    def check_latest_async(self) -> None:
        def work() -> None:
            manifest = self.load_manifest()
            self.manifest = manifest
            self.log_line(f"Najnowsza wersja: {manifest.version}")
            self.log_line("Pliki do flashowania:")
            for file in manifest.files:
                self.log_line(f"  {file.offset}  {file.name}")
            self.after(0, lambda: self.version_var.set(manifest.version))

        self.run_worker(work, "Sprawdzam firmware…")

    def download_firmware(self, manifest: FirmwareManifest, directory: Path) -> FirmwareManifest:
        self.log_line(f"Pobieram firmware {manifest.version}…")
        downloaded: list[FirmwareFile] = []
        for file in manifest.files:
            target = directory / file.name
            self.log_line(f"  GET {file.url}")
            data = self.urlopen_bytes(file.url, timeout=60)
            if len(data) < 1024:
                raise RuntimeError(f"Plik {file.name} jest podejrzanie mały ({len(data)} B).")
            target.write_bytes(data)
            self.log_line(f"  zapisano {target.name}: {len(data) / 1024:.1f} KB")
            downloaded.append(FirmwareFile(file.name, file.url, file.offset, target))
        return FirmwareManifest(manifest.version, manifest.chip, manifest.flash_size, manifest.baud, downloaded)

    def flash_async(self) -> None:
        port = self.selected_port()
        if not port:
            messagebox.showwarning(APP_NAME, "Nie wybrano portu COM. Zainstaluj sterownik i kliknij „Odśwież porty”.")
            return

        def work() -> None:
            manifest = self.manifest or self.load_manifest()
            baud = int(self.baud_var.get() or manifest.baud or 460800)
            with tempfile.TemporaryDirectory(prefix="airguard-flash-") as tmp:
                downloaded = self.download_firmware(manifest, Path(tmp))
                self._flash_with_retries(downloaded, port, baud)
            self.log_line("\n✅ Gotowe. Urządzenie powinno się zrestartować.")
            self.after(0, lambda: messagebox.showinfo(APP_NAME, f"Wgrano AirGuard {manifest.version}."))

        self.run_worker(work, "Flashuję…")

    def _flash_with_retries(self, manifest: FirmwareManifest, port: str, baud: int) -> None:
        speeds = [baud]
        if baud != 115200:
            speeds.append(115200)

        last_error: Exception | None = None
        for index, speed in enumerate(speeds, start=1):
            try:
                if index > 1:
                    self.log_line("\nPierwsza próba nie wyszła. Próbuję wolniej: 115200 baud…")
                    self.log_line("Jeśli dalej nie działa: przytrzymaj BOOT, kliknij Flash, puść BOOT gdy zacznie pisać.")
                self._run_esptool(manifest, port, speed)
                return
            except Exception as exc:
                last_error = exc
                self.log_line(f"Próba {index} nieudana: {exc}")
                time.sleep(1)
        raise RuntimeError(f"Flashowanie nie powiodło się. Ostatni błąd: {last_error}")

    def _run_esptool(self, manifest: FirmwareManifest, port: str, baud: int) -> None:
        try:
            import esptool
        except Exception as exc:
            raise RuntimeError("Brak modułu esptool. Zbuduj .exe przez build_exe.ps1.") from exc

        args = [
            "--chip",
            manifest.chip,
            "-p",
            port,
            "-b",
            str(baud),
            "--before",
            "default_reset",
            "--after",
            "hard_reset",
        ]
        if self.erase_var.get():
            erase_args = args + ["erase_flash"]
            self.log_line("\nUruchamiam erase_flash…")
            self._call_esptool(esptool, erase_args)

        write_args = args + [
            "write_flash",
            "--flash_mode",
            "dio",
            "--flash_size",
            manifest.flash_size,
            "--flash_freq",
            "80m",
        ]
        for file in manifest.files:
            if file.path is None:
                raise RuntimeError(f"Plik {file.name} nie został pobrany")
            write_args.extend([file.offset, str(file.path)])

        self.log_line("\nUruchamiam esptool:")
        self.log_line("esptool.py " + " ".join(write_args))
        self._call_esptool(esptool, write_args)

    def _call_esptool(self, esptool_module, args: list[str]) -> None:
        writer = QueueWriter(self.log)
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            try:
                esptool_module.main(args)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
                if code != 0:
                    raise RuntimeError(f"esptool zakończył z kodem {code}") from exc

    def show_drivers(self) -> None:
        win = tk.Toplevel(self)
        win.title("Sterowniki USB")
        win.geometry("560x300")
        frame = ttk.Frame(win, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Jeśli Windows nie pokazuje portu COM, zainstaluj jeden z driverów:", wraplength=520).pack(anchor="w", pady=(0, 10))
        for name, url in DRIVER_LINKS.items():
            ttk.Button(frame, text=f"Otwórz: {name}", command=lambda u=url: webbrowser.open(u)).pack(anchor="w", pady=4)
        ttk.Label(frame, text="Najczęściej: CP210x albo CH340. Po instalacji odłącz i podłącz USB ponownie.", wraplength=520).pack(anchor="w", pady=(12, 0))

    def show_boot_help(self) -> None:
        messagebox.showinfo(
            "Pomoc przy flashowaniu",
            "Jeśli flashowanie nie startuje:\n\n"
            "1. Użyj kabla USB z danymi, nie tylko ładowania.\n"
            "2. Zamknij Serial Monitor / Arduino / inne programy używające COM.\n"
            "3. Kliknij Odśwież porty.\n"
            "4. Przytrzymaj BOOT na urządzeniu, kliknij flash, puść BOOT gdy zobaczysz 'Writing'.\n"
            "5. Spróbuj prędkości 115200.\n"
            "6. Dla nowego urządzenia zaznacz 'Wyczyść flash'.",
        )

    def open_device_manager(self) -> None:
        if sys.platform.startswith("win"):
            os.system("start devmgmt.msc")
        else:
            messagebox.showinfo(APP_NAME, "Menedżer urządzeń działa tylko na Windows.")


if __name__ == "__main__":
    app = AirGuardFlasher()
    app.mainloop()
