"""Notification-area (tray) icon for the running hot folder."""
from __future__ import annotations

import logging
import os
import threading

import pystray
from PIL import Image

import labelprinter as lp

log = logging.getLogger("labelprinter.tray")


def _icon_image() -> Image.Image:
    for p in (lp.RESOURCE_DIR / "labelbridge.ico", lp.APP_DIR / "labelbridge.ico"):
        if p.exists():
            return Image.open(p)
    return Image.new("RGB", (64, 64), (255, 112, 40))


def run(cfg: dict) -> None:
    stop = threading.Event()

    def open_inbox(icon=None, item=None):
        cfg["inbox"].mkdir(parents=True, exist_ok=True)
        os.startfile(cfg["inbox"])

    def quit_app(icon, item):
        log.info("quit from tray")
        stop.set()
        icon.stop()

    icon = pystray.Icon(
        "LabelBridge", _icon_image(), f"{lp.APP_NAME}: drop label PDFs in the Inbox",
        menu=pystray.Menu(
            pystray.MenuItem("Open labels folder", open_inbox, default=True),
            pystray.MenuItem("Settings…", lambda i, it: lp.launch("settings")),
            pystray.MenuItem("Print a test label", lambda i, it: lp.launch("test")),
            pystray.MenuItem("Show log", lambda i, it: os.startfile(lp.LOG_PATH)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"Quit {lp.APP_NAME}", quit_app),
        ))

    def notify(kind: str, msg: str) -> None:
        try:
            if kind == "warning" and not lp.HEALTH[0]:
                icon.title = f"{lp.APP_NAME}: ⚠ {msg}"[:127]
            elif kind == "info":
                icon.title = f"{lp.APP_NAME}: drop label PDFs in the Inbox"
            icon.notify(msg[:250], lp.APP_NAME)
        except Exception:
            log.exception("tray notification failed")

    lp.on_event = notify
    worker = threading.Thread(target=lp.watch, args=(cfg, stop), name="watch", daemon=True)
    worker.start()
    icon.run()
    stop.set()
    worker.join(timeout=5)
    os._exit(0)  # zeroconf/http threads shouldn't keep the process alive
