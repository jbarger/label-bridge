"""Settings window: printer, paper size, phone pairing code, watched folders, test print."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import labelprinter as lp

log = logging.getLogger("labelprinter.settings")
AUTO_PRINTER = "Automatic (first label printer found)"
AUTO_PAPER = "Automatic (the driver's 4x6 size)"


def _public_networks() -> list[str]:
    """Names of connected networks Windows treats as Public (phones can't reach the PC on those)."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetConnectionProfile | Select-Object Name,NetworkCategory | ConvertTo-Json"],
            capture_output=True, text=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        data = json.loads(out.stdout or "[]")
        data = data if isinstance(data, list) else [data]
        return [d["Name"] for d in data if d.get("NetworkCategory") in (0, "Public")]
    except Exception:
        return []


class SettingsWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.raw = lp.load_raw_config()
        root.title(f"{lp.APP_NAME} settings")
        root.resizable(False, False)
        ico = lp.RESOURCE_DIR / "labelbridge.ico"
        if ico.exists():
            try:
                root.iconbitmap(str(ico))
            except tk.TclError:
                pass

        f = ttk.Frame(root, padding=16)
        f.grid(sticky="nsew")
        f.columnconfigure(1, weight=1)
        r = 0

        self.status = ttk.Label(f, font=("Segoe UI", 10, "bold"))
        self.status.grid(row=r, column=0, columnspan=2, sticky="w")
        self.start_btn = ttk.Button(f, text=f"Start {lp.APP_NAME}", command=self.start_watcher)
        self.start_btn.grid(row=r, column=2, sticky="e")
        r += 1

        # --- printer
        ttk.Separator(f).grid(row=r, column=0, columnspan=3, sticky="ew", pady=10); r += 1
        ttk.Label(f, text="Printer").grid(row=r, column=0, sticky="w")
        try:
            printers = lp.list_printers()
        except Exception:
            printers = []
        self.printer = ttk.Combobox(f, state="readonly", width=48, values=[AUTO_PRINTER, *printers])
        cur = self.raw.get("printer", "auto")
        self.printer.set(AUTO_PRINTER if cur == "auto" else cur)
        self.printer.grid(row=r, column=1, columnspan=2, sticky="ew", pady=2)
        self.printer.bind("<<ComboboxSelected>>", lambda e: self.refresh_papers())
        r += 1
        ttk.Label(f, text="Label size").grid(row=r, column=0, sticky="w")
        self.paper = ttk.Combobox(f, state="readonly", width=48)
        self.paper.grid(row=r, column=1, columnspan=2, sticky="ew", pady=2)
        r += 1
        self.printer_note = ttk.Label(f, foreground="#555")
        self.printer_note.grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1
        ttk.Button(f, text="Save and print a test label", command=self.test_print).grid(
            row=r, column=1, sticky="w", pady=(4, 0))
        r += 1

        # --- phone
        ttk.Separator(f).grid(row=r, column=0, columnspan=3, sticky="ew", pady=10); r += 1
        self.server_enabled = tk.BooleanVar(value=bool(self.raw.get("server_enabled", True)))
        ttk.Checkbutton(f, text="Allow printing from phones on this Wi-Fi (Label Bridge Android app)",
                        variable=self.server_enabled).grid(row=r, column=0, columnspan=3, sticky="w")
        r += 1
        ttk.Label(f, text="Pairing code").grid(row=r, column=0, sticky="w")
        self.code = tk.StringVar(value=self.raw.get("server_token", ""))
        ttk.Label(f, textvariable=self.code, font=("Consolas", 20, "bold")).grid(row=r, column=1, sticky="w")
        ttk.Button(f, text="New code", command=self.new_code).grid(row=r, column=2, sticky="e")
        r += 1
        ip = self._ip()
        ttk.Label(f, foreground="#555", wraplength=460, justify="left", text=(
            "On the phone: install Label Bridge from Google Play, open it, type this code and tap "
            f"\"Find my PC\". If it can't find the PC, type this address instead: {ip}")).grid(
            row=r, column=1, columnspan=2, sticky="w")
        r += 1
        self.net_warn = ttk.Label(f, foreground="#b00020", wraplength=460, justify="left")
        self.net_warn.grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1

        # --- folders
        ttk.Separator(f).grid(row=r, column=0, columnspan=3, sticky="ew", pady=10); r += 1
        ttk.Label(f, text="Labels folder").grid(row=r, column=0, sticky="nw")
        inbox = lp.resolve_path(self.raw.get("inbox", "Inbox"))
        ttk.Label(f, text=str(inbox), wraplength=380).grid(row=r, column=1, sticky="w")
        ttk.Button(f, text="Open", command=lambda: self._open(inbox)).grid(row=r, column=2, sticky="e")
        r += 1
        ttk.Label(f, text="Also watch").grid(row=r, column=0, sticky="nw", pady=(6, 0))
        self.extra = tk.Listbox(f, height=3, width=50)
        for p in self.raw.get("extra_inboxes", []):
            self.extra.insert("end", p)
        self.extra.grid(row=r, column=1, sticky="ew", pady=(6, 0))
        bf = ttk.Frame(f)
        bf.grid(row=r, column=2, sticky="ne", pady=(6, 0))
        ttk.Button(bf, text="Add…", command=self.add_folder).pack(fill="x")
        ttk.Button(bf, text="Remove", command=self.remove_folder).pack(fill="x", pady=(4, 0))
        r += 1
        ttk.Label(f, foreground="#555", wraplength=460, justify="left", text=(
            "Tip: add a Google Drive or OneDrive folder here to print from anywhere by saving a PDF into it.")).grid(
            row=r, column=1, columnspan=2, sticky="w")
        r += 1

        # --- advanced
        ttk.Separator(f).grid(row=r, column=0, columnspan=3, sticky="ew", pady=10); r += 1
        self.preview_only = tk.BooleanVar(value=bool(self.raw.get("preview_only", False)))
        ttk.Checkbutton(f, text="Preview only: save PNGs to Previews instead of printing",
                        variable=self.preview_only).grid(row=r, column=0, columnspan=2, sticky="w")
        ttk.Button(f, text="More settings…", command=lambda: self._open(lp.CONFIG_PATH)).grid(
            row=r, column=2, sticky="e")
        r += 1

        bar = ttk.Frame(f)
        bar.grid(row=r, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(bar, text="Save", command=self.save_and_close).pack(side="left")
        ttk.Button(bar, text="Cancel", command=root.destroy).pack(side="left", padx=(8, 0))

        self.refresh_papers(initial=True)
        self.refresh_status()
        threading.Thread(target=self._check_network, daemon=True).start()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _ip() -> str:
        try:
            import phone_server
            return phone_server.local_ip()
        except Exception:
            return "this PC's IP address"

    @staticmethod
    def _open(path) -> None:
        try:
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
            os.startfile(path)
        except OSError as e:
            messagebox.showerror(lp.APP_NAME, str(e))

    def _check_network(self) -> None:
        public = _public_networks()
        if public:
            msg = (f"Your network \"{', '.join(public)}\" is set to Public, so phones can't reach this PC. "
                   "In Windows Settings → Network, open it and choose Private.")
            try:
                self.root.after(0, lambda: self.net_warn.configure(text=msg))
            except (RuntimeError, tk.TclError):  # window already closed
                pass

    def selected_printer(self) -> str:
        v = self.printer.get()
        return "auto" if v == AUTO_PRINTER else v

    def refresh_papers(self, initial: bool = False) -> None:
        cfg = lp.load_config()
        cfg["printer"] = self.selected_printer()
        try:
            name = lp.find_printer(cfg)
            papers = lp.paper_sizes(name)
            auto_id = lp.choose_paper(name, dict(cfg, paper="auto"))
            auto_name = next((n for pid, n, _ in papers if pid == auto_id), None)
            note = f"Using: {name}" + (f" · auto size: {auto_name}" if auto_name
                                       else " · no 4x6 size in this driver, a custom 4x6 size will be used")
        except Exception as e:
            papers, note = [], f"⚠ {e}"
        self.printer_note.configure(text=note)
        names = [n for _, n, _ in papers]
        self.paper.configure(values=[AUTO_PAPER, *names])
        cur = self.raw.get("paper", "auto") if initial else "auto"
        self.paper.set(cur if cur in names else AUTO_PAPER)

    def refresh_status(self) -> None:
        running = lp.is_running()
        self.status.configure(text=f"● {lp.APP_NAME} is running" if running else f"○ {lp.APP_NAME} is not running",
                              foreground="#1b7f3b" if running else "#b00020")
        self.start_btn.state(["disabled"] if running else ["!disabled"])
        self.root.after(3000, self.refresh_status)

    # ------------------------------------------------------------------ actions
    def start_watcher(self) -> None:
        lp.launch("watch")

    def new_code(self) -> None:
        if messagebox.askyesno(lp.APP_NAME, "Make a new pairing code? Phones paired with the old code "
                                            "will need the new one typed in."):
            self.code.set(lp.new_pairing_code())

    def add_folder(self) -> None:
        d = filedialog.askdirectory(title="Choose a folder to watch for label PDFs")
        if d:
            self.extra.insert("end", os.path.normpath(d))

    def remove_folder(self) -> None:
        for i in reversed(self.extra.curselection()):
            self.extra.delete(i)

    def save(self) -> None:
        raw = lp.load_raw_config()  # keep keys edited by hand
        raw.update(
            printer=self.selected_printer(),
            paper="auto" if self.paper.get() in ("", AUTO_PAPER) else self.paper.get(),
            server_enabled=self.server_enabled.get(),
            server_token=self.code.get(),
            extra_inboxes=list(self.extra.get(0, "end")),
            preview_only=self.preview_only.get(),
        )
        raw.pop("paper_name_contains", None)
        lp.save_raw_config(raw)
        self.raw = raw

    def test_print(self) -> None:
        self.save()
        cfg = lp.load_config()
        cfg["preview_only"] = False
        try:
            lp.print_pdf(lp.test_label_pdf(), cfg, f"{lp.APP_NAME} test label")
        except Exception as e:
            log.exception("test print failed")
            messagebox.showerror(lp.APP_NAME, f"Test print failed:\n\n{e}")
            return
        messagebox.showinfo(lp.APP_NAME, "Test label sent. The thick border should sit just inside the "
                                         "edges of the label.")

    def save_and_close(self) -> None:
        self.save()
        if not lp.is_running():
            lp.launch("watch")
        self.root.destroy()


def run() -> None:
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on high-DPI screens
    except Exception:
        pass
    root = tk.Tk()
    SettingsWindow(root)
    root.mainloop()
