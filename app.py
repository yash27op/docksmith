"""Local-only web service. No third-party Python dependencies."""
import io
import json
import os
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import zipfile

from core import ModelError, demo, generate

STATIC = Path(__file__).parent / "static"
GENERATION_SLOT = threading.BoundedSemaphore(1)


class Handler(BaseHTTPRequestHandler):
    def send(self, status, data, content_type="application/json", **headers):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for key, value in headers.items():
            self.send_header(key.replace("_", "-"), value)
        self.end_headers()
        self.wfile.write(data)

    def reply(self, status, obj):
        self.send(status, json.dumps(obj).encode())

    def do_GET(self):
        if self.path == "/api/health":
            self.reply(200, {"status": "ok", "inference_checked": False})
        elif self.path in ("/", "/app.js", "/style.css"):
            name = "index.html" if self.path == "/" else self.path[1:]
            kind = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}[name]
            self.send(200, (STATIC / name).read_bytes(), kind + "; charset=utf-8")
        else:
            self.reply(404, {"error": "Not found"})

    def do_POST(self):
        if self.path not in ("/api/generate", "/api/demo", "/api/download"):
            self.reply(404, {"error": "Not found"})
            return
        # JSON-only, no CORS: cross-origin browser forms cannot trigger inference.
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.reply(415, {"error": "Use application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 131072:
                self.reply(413, {"error": "Body must be between 1 byte and 128 KiB"})
                return
            self.connection.settimeout(10)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete body")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Expected an object")
            if self.path == "/api/demo":
                self.reply(200, demo())
            elif self.path == "/api/download":
                files = {"Dockerfile": data.get("dockerfile"), ".dockerignore": data.get("dockerignore"),
                         "NOTES.txt": data.get("explanation")}
                if any(not isinstance(v, str) or len(v) > 50000 for v in files.values()):
                    raise ValueError("Invalid download content")
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                    for name, content in files.items():
                        archive.writestr(name, content)
                self.send(200, buffer.getvalue(), "application/zip",
                          Content_Disposition='attachment; filename="docksmith.zip"')
            elif not GENERATION_SLOT.acquire(blocking=False):
                self.reply(429, {"error": "Another generation is running. Try again shortly."})
            else:
                try:
                    self.reply(200, generate(data))
                finally:
                    GENERATION_SLOT.release()
        except (ValueError, UnicodeError) as exc:
            self.reply(400, {"error": str(exc)})
        except ModelError as exc:
            self.reply(502, {"error": str(exc)})
        except TimeoutError:
            self.reply(408, {"error": "Request body timed out"})


def main():
    server = ThreadingHTTPServer((os.getenv("APP_HOST", "127.0.0.1"), int(os.getenv("PORT", "8000"))), Handler)
    print(f"Docksmith listening on {server.server_address}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
