"""CareCircle local server — stdlib http.server over app.web.handle()."""

from __future__ import annotations

import sys
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from . import web


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _dispatch(self, method: str) -> None:
        parts = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        cookies = {}
        raw = self.headers.get("Cookie")
        if raw:
            jar = SimpleCookie()
            jar.load(raw)
            cookies = {k: morsel.value for k, morsel in jar.items()}
        status, headers, payload = web.handle(
            method, parts.path, parts.query, body, cookies)
        self.send_response(status)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(payload)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def log_message(self, *args):  # keep the console quiet
        pass


def main(port: int = 8790) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"CareCircle running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8790)
