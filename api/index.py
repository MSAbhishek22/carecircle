"""CareCircle on Vercel — WSGI entrypoint (serverless adaptation).

The care logic is unchanged (app/core.py + app/web.py); this file is only a
transport adapter. Vercel's Python runtime calls ``app(environ,
start_response)``. Route-for-route parity with app/server.py because both
delegate to ``app.web.handle``.

State caveat (documented in the README): the care profile lives in a
module-level in-memory store, so on serverless it persists only for the
life of a warm instance and can differ across instances. The demo uses
synthetic data for a single profile, which makes this acceptable for
judging; a production version would move the store to a database.
"""

import os
import sys
from http.cookies import SimpleCookie
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import web  # noqa: E402


def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/") or "/"
    query = environ.get("QUERY_STRING", "")
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    body = environ["wsgi.input"].read(length) if length else b""
    cookies = {}
    raw = environ.get("HTTP_COOKIE")
    if raw:
        jar = SimpleCookie()
        jar.load(raw)
        cookies = {k: morsel.value for k, morsel in jar.items()}
    status, headers, payload = web.handle(method, path, query, body, cookies)
    reason = {200: "OK", 201: "Created", 400: "Bad Request",
              401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
              500: "Internal Server Error"}.get(status, "OK")
    start_response(f"{status} {reason}", headers)
    return [payload]
