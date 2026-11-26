"""Built-in web server (standard library only): the UI, its static files and a small REST API."""
import base64
import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import qh_boards
import qh_engine as E
import qh_font as font
import qh_script
import qh_sys
import qh_tz
from qh_hw import RGB_BITS

mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")


def start(app, port, assets_dir, info, frontend_dir=None):
    """`app` is the Engine (master) or the NodeAgent; `info` describes this run.

    When a built React app is available, serve it at `/` while keeping `/static/*`
    rooted at the legacy assets directory for Blockly and Help resources.
    """
    assets_dir = os.path.realpath(assets_dir)
    frontend_dir = os.path.realpath(frontend_dir) if frontend_dir and os.path.isfile(
        os.path.join(frontend_dir, "index.html")) else None
    info = dict(info)
    info.setdefault("web_port", port)

    class H(BaseHTTPRequestHandler):
        server_version = "QHome/" + E.VERSION
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _auth_ok(self):
            pw = app.cfg["device"].get("web_password") or ""
            if not pw:
                return True
            h = self.headers.get("Authorization", "")
            if h.startswith("Basic "):
                try:
                    return base64.b64decode(h[6:]).decode().split(":", 1)[1] == pw
                except Exception:
                    return False
            return False

        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None, cache=False):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False)
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _file(self, rel, cache=False, root=None):
            root = root or assets_dir
            path = os.path.realpath(os.path.join(root, rel))
            if os.path.commonpath((root, path)) != root or not os.path.isfile(path):
                return self._send(404, {"error": "not found"})
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            with open(path, "rb") as f:
                self._send(200, f.read(), ctype, cache=cache)

        def do_GET(self):
            if not self._auth_ok():
                return self._send(401, {"error": "password required"},
                                  extra={"WWW-Authenticate": 'Basic realm="QHome"'})
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                return self._file("index.html", root=frontend_dir or assets_dir)
            if u.path.startswith("/static/"):
                rel = u.path[8:]
                return self._file(rel, cache=rel.startswith(("vendor/", "fonts/")))
            if frontend_dir and u.path.startswith("/assets/"):
                return self._file(u.path[1:], cache=True, root=frontend_dir)
            if u.path == "/api/meta":
                return self._send(200, dict(info, types=E.TYPES, models=qh_boards.public_models(),
                                            colors=list(RGB_BITS), version=E.VERSION,
                                            entity_fields=qh_script.ENTITY_FIELDS, sys=qh_sys.static_info(),
                                            matrix={"modes": list(font.MODES), "anims": list(font.ANIMS),
                                                    "icons": {n: font.icon(n, 7) for n in font.ICONS}},
                                            tz={"zones": qh_tz.zones(), "fixed": qh_tz.fixed_names(),
                                                "db": bool(qh_tz.zones()), "default": qh_tz.DEFAULT}))
            if u.path == "/api/config":
                return self._send(200, app.cfg)
            if u.path == "/api/state":
                since = int((parse_qs(u.query).get("log") or ["0"])[0] or 0)
                snap = app.snapshot(since)
                snap["sys"] = qh_sys.last()          # main.py takes the samples; here they are only read
                snap["time"] = qh_tz.describe(app.cfg["device"].get("tz") or qh_tz.DEFAULT)
                return self._send(200, snap)
            if u.path == "/api/ports":
                return self._send(200, app.ports.list() if getattr(app, "ports", None) else [])
            if u.path == "/api/export":
                return self._send(200, json.dumps(app.cfg, ensure_ascii=False, indent=2), extra={
                    "Content-Disposition": 'attachment; filename="qhome-config.json"'})
            if frontend_dir and not u.path.startswith("/api/"):
                return self._file("index.html", root=frontend_dir)
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._auth_ok():
                return self._send(401, {"error": "password required"},
                                  extra={"WWW-Authenticate": 'Basic realm="QHome"'})
            u = urlparse(self.path)
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 4_000_000:
                    raise ValueError("request too large")
                data = json.loads(self.rfile.read(n) or b"{}")
            except Exception as e:
                return self._send(400, {"ok": False, "errors": ["Not valid JSON: %s" % e]})
            if not isinstance(data, dict):
                return self._send(400, {"ok": False, "errors": ["Not valid JSON: an object is expected"]})
            if u.path == "/api/config":
                old_role = app.cfg["device"].get("role", "master")
                try:
                    errs = app.submit_config(data)
                except Exception as e:
                    errs = ["This setup could not be read: %r" % e]
                restart = not errs and (data.get("device") or {}).get("role", "master") != old_role
                if restart:
                    app.want_restart = True
                return self._send(200 if not errs else 422,
                                  {"ok": not errs, "errors": errs, "restart": restart})
            if u.path == "/api/cmd":
                app.submit_command(data.get("id"), data.get("action"), data.get("value"))
                return self._send(200, {"ok": True})
            if u.path == "/api/sim":
                if "discover" in data:               # pretend a new board was found (simulator only)
                    ok = getattr(app, "sim_discover", lambda e: False)(data["discover"])
                else:
                    ok = app.sim_input(data.get("board"), data.get("pin"), data.get("value"))
                return self._send(200, {"ok": bool(ok)})
            self._send(404, {"error": "not found"})

    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True, name="web").start()
    app.log("Web UI ready on port %d" % port)
    return srv
