"""Label Bridge for Windows: a hot folder that prints shipping labels on any 4x6 printer.

Drop a PDF into the Inbox folder; each page is cropped to the actual label
content, rotated to portrait if needed, scaled to fill a 4x6 label and sent
straight to the printer. The PDF is then moved to Printed/ (or Failed/ with an
error log next to it). Phones running the Label Bridge Android app can send
labels too (see phone_server.py).

Usage (LabelBridge.exe takes the same commands):
    labelprinter.py watch               # hot folder + phone server + tray icon
    labelprinter.py watch --no-tray     # same, without the tray icon (Ctrl+C stops)
    labelprinter.py settings            # settings window
    labelprinter.py preview FILE.pdf    # write cropped preview PNGs only
    labelprinter.py print FILE.pdf      # crop + print one file now (doesn't move it)
    labelprinter.py test                # print the built-in test label
    labelprinter.py printers            # list installed printers
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import logging
import logging.handlers
import os
import secrets
import shutil
import subprocess
import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pymupdf
from PIL import Image

APP_NAME = "Label Bridge"
VERSION = "2.0.0"

FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))


def _documents() -> Path:
    try:
        from win32com.shell import shell, shellcon
        return Path(shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0))
    except Exception:
        return Path.home() / "Documents"


# Where config.json and the log live. A source checkout that has its own
# config.json keeps everything next to the code (handy for development);
# an installed copy uses %LOCALAPPDATA%\Label Bridge, and puts the label
# folders in Documents\Label Bridge where people can find them.
if os.environ.get("LABELBRIDGE_HOME"):
    DATA_DIR = Path(os.environ["LABELBRIDGE_HOME"])
    FOLDERS_BASE = DATA_DIR
elif not FROZEN and (APP_DIR / "config.json").exists():
    DATA_DIR = FOLDERS_BASE = APP_DIR
else:
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
    FOLDERS_BASE = _documents() / APP_NAME
CONFIG_PATH = DATA_DIR / "config.json"
LOG_PATH = DATA_DIR / "labelbridge.log"

DEFAULT_CONFIG = {
    "printer": "auto",                 # exact Windows printer name, or "auto" = first one that looks like a label printer
    "paper": "auto",                   # exact driver paper name, or "auto" = the driver's 4x6 / 100x150 mm size
    "label_width_in": 4.0,
    "label_height_in": 6.0,
    "dpi": 203,                        # only used for previews when preview_only is on; printing uses the printer's own resolution
    "inbox": "Inbox",                  # relative paths are inside Documents\Label Bridge
    "extra_inboxes": [],               # more watched folders, e.g. a Google Drive folder synced to this PC
    "printed_dir": "Printed",
    "failed_dir": "Failed",
    "preview_dir": "Previews",
    "preview_only": False,             # true = make preview PNGs in Previews/ but never print
    "poll_seconds": 2.0,
    "min_gap_in": 0.2,                 # blank gap that separates the label from other page content
    "margin_in": 0.08,                 # white border kept around the detected content
    "rotate_landscape": "clockwise",   # "clockwise" or "counterclockwise"
    "bw_threshold": 170,               # 0-255; grey darker than this prints black
    "server_enabled": True,            # accept labels from the Label Bridge phone app over home Wi-Fi
    "server_port": 8765,
    "server_token": "",                # pairing code the phone app must send; generated on first run
}
PATH_KEYS = ("inbox", "printed_dir", "failed_dir", "preview_dir")

# Printer names that are almost certainly 4x6 label printers, for "auto".
LABEL_PRINTER_HINTS = (
    "d450", "d-450", "rollo", "zebra", "zp4", "zp5", "zd4", "zd6", "gk420", "gx420", "lp2844",
    "munbyn", "polono", "itari", "phomemo", "jadens", "idprt", "xprinter", "beeprt", "arkscan",
    "nelko", "hprt", "vretti", "omezizy", "4x6", "4 x 6", "label", "thermal",
)

log = logging.getLogger("labelprinter")

# Called with (kind, message) for things worth showing the user (the tray uses it).
on_event: Callable[[str, str], None] = lambda kind, msg: None


# --------------------------------------------------------------------------- config

def new_pairing_code() -> str:
    return "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(6))


def load_raw_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")))  # Notepad may add a BOM
    return cfg


def save_raw_config(raw: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)


def ensure_config() -> bool:
    """Create config.json with a fresh pairing code if there isn't one. True if it was created."""
    if CONFIG_PATH.exists():
        raw = load_raw_config()
        if not raw.get("server_token"):
            raw["server_token"] = new_pairing_code()
            save_raw_config(raw)
        return False
    save_raw_config(dict(DEFAULT_CONFIG, server_token=new_pairing_code()))
    return True


def resolve_path(p: str | Path) -> Path:
    p = Path(os.path.expandvars(str(p)))
    return p if p.is_absolute() else FOLDERS_BASE / p


def load_config() -> dict:
    cfg = load_raw_config()
    for key in PATH_KEYS:
        cfg[key] = resolve_path(cfg[key])
    cfg["extra_inboxes"] = [resolve_path(p) for p in cfg["extra_inboxes"]]
    return cfg


# Outcome of each processed file, keyed by its file name, so the phone server can
# report "printed" / "failed" back to the app.
RESULTS: dict[str, tuple[str, str]] = {}


# --------------------------------------------------------------------------- cropping

@dataclass
class Box:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def area(self) -> int:
        return (self.x1 - self.x0) * (self.y1 - self.y0)


def _runs(flags: np.ndarray, value: bool):
    """Yield (start, end) of runs where flags == value."""
    start = None
    for i, f in enumerate(flags):
        if f == value and start is None:
            start = i
        elif f != value and start is not None:
            yield start, i
            start = None
    if start is not None:
        yield start, len(flags)


def _xy_cut(ink: np.ndarray, ox: int, oy: int, gap: int, out: list[Box]) -> None:
    """Recursive XY-cut: split the region along blank bands at least `gap` px wide."""
    rows = ink.any(axis=1)
    cols = ink.any(axis=0)
    if not rows.any():
        return
    r0, r1 = np.argmax(rows), len(rows) - np.argmax(rows[::-1])
    c0, c1 = np.argmax(cols), len(cols) - np.argmax(cols[::-1])
    ink = ink[r0:r1, c0:c1]
    ox, oy = ox + c0, oy + r0

    for axis in (0, 1):  # try horizontal bands first, then vertical
        has_ink = ink.any(axis=1 - axis)
        segments, seg_start = [], 0
        for s, e in _runs(has_ink, False):
            if e - s >= gap:
                segments.append((seg_start, s))
                seg_start = e
        if segments:
            segments.append((seg_start, len(has_ink)))
            for s, e in segments:
                if axis == 0:
                    _xy_cut(ink[s:e, :], ox, oy + s, gap, out)
                else:
                    _xy_cut(ink[:, s:e], ox + s, oy, gap, out)
            return
    out.append(Box(ox, oy, ox + ink.shape[1], oy + ink.shape[0]))


def find_label_box(page: pymupdf.Page, cfg: dict, analysis_dpi: int = 150) -> pymupdf.Rect:
    """Return the label's bounding box in page points (displayed orientation)."""
    pix = page.get_pixmap(dpi=analysis_dpi, colorspace=pymupdf.csGRAY, alpha=False)
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    ink = gray < 240  # low bar so faint antialiased border lines still join the label
    if not ink.any():
        raise ValueError("page is blank")
    blocks: list[Box] = []
    _xy_cut(ink, 0, 0, max(2, round(cfg["min_gap_in"] * analysis_dpi)), blocks)
    best = max(blocks, key=lambda b: b.area)
    k = 72.0 / analysis_dpi
    m = cfg["margin_in"] * 72.0
    r = pymupdf.Rect(best.x0 * k - m, best.y0 * k - m, best.x1 * k + m, best.y1 * k + m)
    page_rect = pymupdf.Rect(0, 0, pix.width * k, pix.height * k)
    return r & page_rect


def label_size_px(cfg: dict) -> tuple[int, int]:
    return round(cfg["label_width_in"] * cfg["dpi"]), round(cfg["label_height_in"] * cfg["dpi"])


def render_label(page: pymupdf.Page, cfg: dict, target: tuple[int, int] | None = None) -> Image.Image:
    """Crop, rotate and scale one PDF page to a black-and-white label image of `target` px."""
    tw, th = target or label_size_px(cfg)
    box = find_label_box(page, cfg)
    rotate = (box.width > box.height) != (tw > th)
    cw, ch = (box.height, box.width) if rotate else (box.width, box.height)
    zoom = min(tw / cw, th / ch)

    # Render at exactly the printer's resolution so barcode bars land on whole dots.
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=None, colorspace=pymupdf.csGRAY, alpha=False)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    img = img.crop((round(box.x0 * zoom), round(box.y0 * zoom), round(box.x1 * zoom), round(box.y1 * zoom)))
    if rotate:
        img = img.transpose(Image.Transpose.ROTATE_270 if cfg["rotate_landscape"] == "clockwise"
                            else Image.Transpose.ROTATE_90)
    if img.width > tw or img.height > th:  # rounding guard
        img.thumbnail((tw, th), Image.Resampling.LANCZOS)

    canvas = Image.new("L", (tw, th), 255)
    canvas.paste(img, ((tw - img.width) // 2, (th - img.height) // 2))
    thr = cfg["bw_threshold"]
    return canvas.point(lambda v: 0 if v < thr else 255)


def render_pdf(src: Path | bytes, cfg: dict, target: tuple[int, int] | None = None) -> list[Image.Image]:
    # Open from memory: a PDF that fails to parse must not leave a handle on the file,
    # or it can't be moved to Failed/ afterwards.
    data = src if isinstance(src, (bytes, bytearray)) else Path(src).read_bytes()
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if doc.page_count == 0:
            raise ValueError("PDF has no pages")
        return [render_label(p, cfg, target) for p in doc]


# --------------------------------------------------------------------------- printing

def list_printers() -> list[str]:
    import win32print
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(flags)]


def find_printer(cfg: dict) -> str:
    names = list_printers()
    want = cfg.get("printer") or "auto"
    if want != "auto":
        if want in names:
            return want
        raise RuntimeError(f"printer {want!r} isn't installed; choose one in {APP_NAME} settings")
    for n in names:
        if any(h in n.lower() for h in LABEL_PRINTER_HINTS):
            return n
    raise RuntimeError(f"no label printer found; choose your printer in {APP_NAME} settings")


def paper_sizes(printer: str) -> list[tuple[int, str, tuple[int, int]]]:
    """(paper id, name, (width, height) in 0.1 mm) for every paper the driver offers."""
    import win32con
    import win32print
    h = win32print.OpenPrinter(printer)
    try:
        port = win32print.GetPrinter(h, 2)["pPortName"]
    finally:
        win32print.ClosePrinter(h)
    names = [n.strip("\0") for n in win32print.DeviceCapabilities(printer, port, win32con.DC_PAPERNAMES)]
    ids = win32print.DeviceCapabilities(printer, port, win32con.DC_PAPERS)
    sizes = win32print.DeviceCapabilities(printer, port, win32con.DC_PAPERSIZE)
    sizes = [(s["x"], s["y"]) if isinstance(s, dict) else tuple(s) for s in sizes]
    return list(zip(ids, names, sizes))


def choose_paper(printer: str, cfg: dict) -> int | None:
    """Driver paper id to use, or None if the driver has no 4x6 size (then a custom size is set)."""
    papers = paper_sizes(printer)
    want = cfg.get("paper") or "auto"
    if want != "auto":
        for pid, name, _ in papers:
            if name == want:
                return pid
        log.warning("paper %r not offered by %s; picking the 4x6 size automatically", want, printer)
    legacy = cfg.get("paper_name_contains")  # older config files
    if legacy:
        for pid, name, _ in papers:
            if legacy in name:
                return pid
    tw, th = round(cfg["label_width_in"] * 254), round(cfg["label_height_in"] * 254)
    best, best_err = None, 80  # tolerate up to 8 mm total so 100x150 mm matches 4x6"
    for pid, _, (w, h) in papers:
        err = min(abs(w - tw) + abs(h - th), abs(w - th) + abs(h - tw))
        if err < best_err:
            best, best_err = pid, err
    return best


@contextlib.contextmanager
def printer_dc(cfg: dict):
    """Yield (win32ui DC, printer name, (width, height) printable px) set up for a 4x6 label."""
    import win32con
    import win32gui
    import win32print
    import win32ui

    printer = find_printer(cfg)
    paper = choose_paper(printer, cfg)
    h = win32print.OpenPrinter(printer)
    try:
        dm = win32print.GetPrinter(h, 2)["pDevMode"]
        dm.Orientation = win32con.DMORIENT_PORTRAIT
        dm.Copies = 1
        dm.Fields |= win32con.DM_ORIENTATION | win32con.DM_COPIES | win32con.DM_PAPERSIZE
        if paper is not None:
            dm.PaperSize = paper
            dm.Fields &= ~(win32con.DM_PAPERLENGTH | win32con.DM_PAPERWIDTH)
        else:
            dm.PaperSize = 256  # DMPAPER_USER
            dm.PaperWidth = round(cfg["label_width_in"] * 254)
            dm.PaperLength = round(cfg["label_height_in"] * 254)
            dm.Fields |= win32con.DM_PAPERLENGTH | win32con.DM_PAPERWIDTH
        win32print.DocumentProperties(0, h, printer, dm, dm, win32con.DM_IN_BUFFER | win32con.DM_OUT_BUFFER)
    finally:
        win32print.ClosePrinter(h)

    dc = win32ui.CreateDCFromHandle(win32gui.CreateDC("WINSPOOL", printer, dm))
    try:
        size = dc.GetDeviceCaps(win32con.HORZRES), dc.GetDeviceCaps(win32con.VERTRES)
        yield dc, printer, size
    finally:
        dc.DeleteDC()


def print_pdf(src: Path | bytes, cfg: dict, doc_name: str) -> list[Image.Image]:
    """Render a PDF at the printer's own resolution and print one label per page."""
    if cfg["preview_only"]:
        return render_pdf(src, cfg)
    from PIL import ImageWin
    with printer_dc(cfg) as (dc, printer, (pw, ph)):
        images = render_pdf(src, cfg, (pw, ph))
        dc.StartDoc(doc_name)
        for img in images:
            dc.StartPage()
            ImageWin.Dib(img).draw(dc.GetHandleOutput(), (0, 0, pw, ph))
            dc.EndPage()
        dc.EndDoc()
    log.info("sent %d label(s) from %s to %s", len(images), doc_name, printer)
    return images


def test_label_pdf() -> bytes:
    """A letter page with a 4x6 label in one corner plus 'instructions' text, like a carrier PDF."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    x0, y0, x1, y1 = 36, 36, 36 + 288, 36 + 432
    page.draw_rect(pymupdf.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=3)
    page.insert_text((x0 + 16, y0 + 40), APP_NAME, fontsize=26, fontname="helv")
    page.insert_text((x0 + 16, y0 + 66), "Test label", fontsize=16, fontname="helv")
    page.insert_text((x0 + 16, y0 + 92), _dt.datetime.now().strftime("%Y-%m-%d %H:%M"), fontsize=11)
    page.draw_line((x0, y0 + 110), (x1, y0 + 110), width=2)
    lines = ["If the border is just inside the", "edges of the label, you're all set.",
             "", "Edges cut off? Raise margin_in.", "Text too faint? Raise bw_threshold."]
    for i, s in enumerate(lines):
        page.insert_text((x0 + 16, y0 + 138 + i * 18), s, fontsize=12)
    bars = [3, 1, 2, 1, 1, 3, 1, 2, 2, 1, 3, 1, 1, 2, 2, 1, 1, 3, 2, 1, 1, 2, 3, 1, 2, 1, 1, 3, 1, 2]
    x, unit = x0 + 24.0, 240 / sum(bars)
    for i, b in enumerate(bars):
        if i % 2 == 0:
            page.draw_rect(pymupdf.Rect(x, y1 - 150, x + b * unit, y1 - 40), color=None, fill=(0, 0, 0))
        x += b * unit
    page.insert_text((x0 + 340, 120), "Instructions (should NOT print):", fontsize=10)
    page.insert_text((x0 + 340, 136), "Fold here and attach to package.", fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


# --------------------------------------------------------------------------- hot folder

def save_previews(images: list[Image.Image], src: Path, cfg: dict) -> list[Path]:
    cfg["preview_dir"].mkdir(parents=True, exist_ok=True)
    out = []
    for i, img in enumerate(images, 1):
        p = cfg["preview_dir"] / f"{src.stem}{'' if len(images) == 1 else f'_p{i}'}.png"
        img.save(p)
        out.append(p)
    return out


def _unique_dest(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    if dest.exists():
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = folder / f"{Path(name).stem}_{stamp}{Path(name).suffix}"
    return dest


def _move(src: Path, folder: Path) -> Path:
    """Rename into folder; only copy+delete across drives, and never leave a duplicate behind."""
    dest = _unique_dest(folder, src.name)
    try:
        os.rename(src, dest)
    except OSError as e:
        if getattr(e, "winerror", None) != 17:  # 17 = ERROR_NOT_SAME_DEVICE
            raise
        shutil.copy2(src, dest)
        try:
            os.remove(src)
        except OSError:
            dest.unlink(missing_ok=True)
            raise
    return dest


def _record(path: Path, status: str, detail: str) -> None:
    if path.name.startswith("phone_"):  # only the phone server waits on results
        RESULTS[path.name] = (status, detail)


def process_file(path: Path, cfg: dict) -> bool:
    log.info("processing %s", path.name)
    try:
        images = print_pdf(path, cfg, path.name)
        save_previews(images, path, cfg)
        if cfg["preview_only"]:
            log.info("preview_only is on; previews written for %s", path.name)
    except Exception as e:
        err = traceback.format_exc()
        log.error("failed on %s:\n%s", path.name, err)
        try:
            dest = _move(path, cfg["failed_dir"])
            dest.with_suffix(dest.suffix + ".error.txt").write_text(
                f"{_dt.datetime.now():%Y-%m-%d %H:%M:%S}  {path.name}\n\n{err}", encoding="utf-8")
        except Exception:
            log.exception("could not move %s to Failed/", path.name)
        _record(path, "failed", err.strip().splitlines()[-1])
        on_event("error", f"Couldn't print {path.name}: {e}")
        return False
    _record(path, "printed", f"{len(images)} label(s)")
    try:
        _move(path, cfg["printed_dir"])
    except Exception:
        log.exception("printed %s but could not move it to Printed/", path.name)
    return True


def _is_ready(path: Path) -> bool:
    """True once nothing else has the file open for writing (e.g. a browser download)."""
    try:
        with open(path, "rb+"):
            return True
    except OSError:
        return False


def _list_pdfs(folder: Path) -> set[Path]:
    try:
        return {p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"}
    except OSError:  # e.g. Google Drive not mounted yet right after login
        return set()


def _prepare_folders(cfg: dict) -> None:
    for key in PATH_KEYS:
        cfg[key].mkdir(parents=True, exist_ok=True)
    for extra in cfg["extra_inboxes"]:
        try:
            extra.mkdir(parents=True, exist_ok=True)
        except OSError:
            log.warning("extra inbox %s not available yet; will keep checking", extra)


def describe_printer(cfg: dict) -> str:
    if cfg["preview_only"]:
        return "PREVIEW ONLY"
    try:
        return find_printer(cfg)
    except Exception as e:
        return f"none ({e})"


def watch(cfg: dict, stop: threading.Event | None = None) -> None:
    """Poll the inboxes until `stop` is set. `cfg` is updated in place when config.json changes."""
    stop = stop or threading.Event()
    _prepare_folders(cfg)
    log.info("%s %s watching %s (printer: %s)", APP_NAME, VERSION,
             ", ".join(map(str, [cfg["inbox"], *cfg["extra_inboxes"]])), describe_printer(cfg))
    import phone_server
    phone_server.start(cfg, RESULTS)
    cfg_mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0
    last_size: dict[Path, int] = {}
    # Files already attempted but still in the Inbox (their move failed). Keyed by
    # (path, mtime, size) so a re-dropped file with the same name is picked up again,
    # but a stuck one is never printed twice.
    attempted: set[tuple[Path, float, int]] = set()
    while not stop.is_set():
        try:
            mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0
            if mtime != cfg_mtime:
                cfg_mtime = mtime
                try:
                    new = load_config()
                except Exception:
                    log.exception("config.json is invalid; keeping the previous settings")
                else:
                    cfg.clear()
                    cfg.update(new)
                    _prepare_folders(cfg)
                    phone_server.start(cfg, RESULTS)  # no-op if already running
                    log.info("settings reloaded (printer: %s)", describe_printer(cfg))

            inboxes = [cfg["inbox"], *cfg["extra_inboxes"]]
            current = set().union(*(_list_pdfs(f) for f in inboxes))
            for p in sorted(current):
                st = p.stat()
                if (p, st.st_mtime, st.st_size) in attempted:
                    continue
                if st.st_size > 0 and last_size.get(p) == st.st_size and _is_ready(p):
                    last_size.pop(p, None)
                    attempted.add((p, st.st_mtime, st.st_size))
                    process_file(p, cfg)
                else:
                    last_size[p] = st.st_size
            for gone in set(last_size) - current:
                last_size.pop(gone, None)
            attempted = {a for a in attempted if a[0] in current}
        except Exception:
            log.exception("watch loop error")
        stop.wait(cfg["poll_seconds"])


MUTEX_NAME = "Local\\LabelPrinterHotFolder"


def is_running() -> bool:
    import win32api
    import win32event
    try:
        h = win32event.OpenMutex(0x00100000, False, MUTEX_NAME)  # SYNCHRONIZE
    except Exception:
        return False
    win32api.CloseHandle(h)
    return True


def _claim_single_instance():
    import win32api
    import win32event
    import winerror
    mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        return None
    return mutex


def self_command(*args: str) -> list[str]:
    """Command line that runs this program again with `args` (works frozen or from source)."""
    if FROZEN:
        return [sys.executable, *args]
    exe = Path(sys.executable)
    pyw = exe.with_name(exe.name.replace("python", "pythonw", 1)) if "pythonw" not in exe.name else exe
    return [str(pyw if pyw.exists() else exe), str(Path(__file__).resolve()), *args]


def launch(*args: str) -> None:
    subprocess.Popen(self_command(*args), close_fds=True,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


def _setup_logging(console: bool) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8")]
    if console and sys.stdout is not None:  # windowed builds have no console
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    w = sub.add_parser("watch")
    w.add_argument("--no-tray", action="store_true")
    sub.add_parser("settings")
    sub.add_parser("printers")
    sub.add_parser("test")
    for name in ("preview", "print"):
        sp = sub.add_parser(name)
        sp.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args(argv)
    cmd = args.cmd or "watch"  # double-clicking LabelBridge.exe
    no_tray = getattr(args, "no_tray", False)

    _setup_logging(console=cmd != "watch" or no_tray)
    created = ensure_config()
    cfg = load_config()

    if cmd == "settings":
        import settings_gui
        settings_gui.run()
    elif cmd == "printers":
        for p in list_printers():
            print(p)
        print("\nselected:", describe_printer(cfg))
    elif cmd == "preview":
        for f in args.files:
            for p in save_previews(render_pdf(f, cfg), f, cfg):
                print(p)
    elif cmd == "print":
        for f in args.files:
            print_pdf(f, cfg, f.name)
    elif cmd == "test":
        print_pdf(test_label_pdf(), cfg, f"{APP_NAME} test label")
    elif cmd == "watch":
        mutex = _claim_single_instance()  # noqa: F841  (held for the process lifetime)
        if mutex is None:
            log.info("already running; opening settings instead")
            launch("settings")
            return 0
        if created:
            launch("settings")  # first run: pick a printer and see the pairing code
        if no_tray:
            try:
                watch(cfg)
            except KeyboardInterrupt:
                log.info("stopped")
        else:
            import tray
            tray.run(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
