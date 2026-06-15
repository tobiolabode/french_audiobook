from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from french_audiobook.app import app_settings_from_env
from french_audiobook.onedrive import DRIVE_STATE_COOKIE, authorize_url, cookie_header, is_secure_cookie, new_oauth_state


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        settings = app_settings_from_env()
        if not settings.onedrive.enabled:
            self._send_json({"error": "OneDrive auth is not configured."}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        state = new_oauth_state()
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", authorize_url(settings.onedrive, state=state))
        self.send_header(
            "Set-Cookie",
            cookie_header(DRIVE_STATE_COOKIE, state, max_age=600, secure=is_secure_cookie()),
        )
        self.end_headers()

    def _send_json(self, payload: dict[str, str], *, status: HTTPStatus) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
