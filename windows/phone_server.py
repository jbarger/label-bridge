"""Small HTTP endpoint so the Label Bridge Android app can send PDFs over home Wi-Fi.

Runs inside the watcher process (`labelprinter.py watch`). An uploaded PDF is
written into the Inbox, so it goes through exactly the same crop/print/move path
as a dropped file. The request then waits briefly so the phone can show
"Printed" or the error.

    GET  /ping                      -> {"ok": true, "printer": ..., "host": ..., "app": ..., "version": ...}
    POST /print   body = PDF bytes  -> {"status": "printed"|"failed"|"queued", "detail": ...}
         headers: X-Token: <server_token>, X-Filename: <url-encoded original name>

The service is also advertised over mDNS/DNS-SD as _labelprinter._tcp, so the
app can find the PC without anyone typing its IP address.
"""
from __future__ import annotations

import datetime as _dt
import hmac
import json
import logging
import re
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("labelprinter.server")

MAX_BYTES = 30 * 1024 * 1024
WAIT_FOR_RESULT_S = 45


def _safe_name(raw: str) -> str:
    name = Path(urllib.parse.unquote(raw or "")).name
    name = re.sub(r"[^\w .()-]", "_", name).strip(" .") or "label"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name[-90:]


def _local_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))  # no packets are sent; just picks the LAN interface
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def _make_handler(cfg: dict, results: dict):
    # cfg is the live settings dict (updated in place when config.json changes),
    # so a new pairing code or turning phone printing off takes effect immediately.

    class Handler(BaseHTTPRequestHandler):
        server_version = "LabelBridge/2"

        def log_message(self, fmt, *args):  # route http.server logging into our log
            log.info("%s %s", self.client_address[0], fmt % args)

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if not cfg.get("server_enabled", True):
                self._send(403, {"status": "error", "detail": "phone printing is turned off on the PC"})
                return False
            token = str(cfg.get("server_token") or "")
            if token and hmac.compare_digest(self.headers.get("X-Token", "").strip().upper().encode(), token.upper().encode()):
                return True
            self._send(401, {"status": "error", "detail": "wrong pairing code"})
            return False

        def do_GET(self):
            if self.path != "/ping":
                return self._send(404, {"status": "error", "detail": "not found"})
            if self._authorized():
                from labelprinter import APP_NAME, VERSION, describe_printer
                self._send(200, {"ok": True, "printer": describe_printer(cfg), "host": socket.gethostname(),
                                 "app": APP_NAME, "version": VERSION})

        def do_POST(self):
            if self.path != "/print":
                return self._send(404, {"status": "error", "detail": "not found"})
            if not self._authorized():
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BYTES:
                return self._send(413, {"status": "error", "detail": f"file must be 1 byte to {MAX_BYTES // 2**20} MB"})
            data = self.rfile.read(length)
            if not data.startswith(b"%PDF"):
                return self._send(415, {"status": "error", "detail": "that file isn't a PDF"})

            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
            name = f"phone_{stamp}_{_safe_name(self.headers.get('X-Filename', ''))}"
            inbox: Path = cfg["inbox"]
            part = inbox / (name + ".part")  # not *.pdf, so the watcher ignores it until renamed
            part.write_bytes(data)
            part.rename(inbox / name)
            log.info("received %s (%d bytes) from %s", name, len(data), self.client_address[0])

            deadline = time.monotonic() + WAIT_FOR_RESULT_S
            while time.monotonic() < deadline:
                if name in results:
                    status, detail = results.pop(name)
                    return self._send(200, {"status": status, "detail": detail})
                time.sleep(0.25)
            self._send(202, {"status": "queued", "detail": "received; still waiting for the printer"})

    return Handler


def _advertise(port: int):
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError:
        log.warning("zeroconf not installed; the phone app will need the PC's IP typed in")
        return None
    ip = _local_ip()
    host = socket.gethostname()
    info = ServiceInfo(
        "_labelprinter._tcp.local.",
        f"{host}._labelprinter._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={"v": "2", "app": "Label Bridge"},
        server=f"{host.lower()}.local.",
    )
    zc = Zeroconf()
    zc.register_service(info)
    log.info("advertising _labelprinter._tcp on %s:%d", ip, port)
    return zc


_httpd: ThreadingHTTPServer | None = None


def start(cfg: dict, results: dict) -> ThreadingHTTPServer | None:
    """Start the phone endpoint once (later calls do nothing). Port changes need a restart."""
    global _httpd
    if _httpd is not None or not cfg.get("server_enabled", True):
        return _httpd
    if not cfg.get("server_token"):
        log.warning("server_token is empty in config.json; phone printing disabled")
        return None
    port = int(cfg["server_port"])
    try:
        httpd = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(cfg, results))
    except OSError as e:
        log.error("phone server could not use port %d (%s); is another copy running?", port, e)
        return None
    threading.Thread(target=httpd.serve_forever, name="phone-server", daemon=True).start()
    log.info("phone server listening on http://%s:%d", _local_ip(), port)
    try:
        httpd.zeroconf = _advertise(port)  # keep a reference so it isn't garbage-collected
    except Exception:
        log.exception("mDNS advertisement failed; manual IP entry still works")
    _httpd = httpd
    return httpd


def local_ip() -> str:
    return _local_ip()
