from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from french_audiobook.app import app_settings_from_env
from french_audiobook.onedrive import (
    DRIVE_STATE_COOKIE,
    DRIVE_TOKEN_COOKIE,
    OneDriveError,
    cookie_header,
    cookie_value_from_header,
    exchange_code_for_token,
    expired_cookie_header,
    is_secure_cookie,
    signed_cookie_dumps,
)


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        settings = app_settings_from_env()
        if not settings.onedrive.enabled:
            self._send_json({"error": "OneDrive auth is not configured."}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        params = parse_qs(urlparse(self.path).query)
        state = params.get("state", [""])[0]
        code = params.get("code", [""])[0]
        expected_state = cookie_value_from_header(self.headers.get("cookie"), DRIVE_STATE_COOKIE)
        if not state or not expected_state or state != expected_state:
            self._send_json({"error": "Invalid OAuth state."}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            token = exchange_code_for_token(settings.onedrive, code)
        except OneDriveError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus(exc.status))
            return

        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            cookie_header(
                DRIVE_TOKEN_COOKIE,
                signed_cookie_dumps(token, settings.onedrive.cookie_secret),
                max_age=60 * 60 * 24 * 21,
                secure=is_secure_cookie(),
            ),
        )
        self.send_header("Set-Cookie", expired_cookie_header(DRIVE_STATE_COOKIE, secure=is_secure_cookie()))
        self.end_headers()

    def _send_json(self, payload: dict[str, str], *, status: HTTPStatus) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
