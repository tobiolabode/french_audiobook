from __future__ import annotations

import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from french_audiobook.onedrive import DRIVE_STATE_COOKIE, DRIVE_TOKEN_COOKIE, expired_cookie_header, is_secure_cookie


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Set-Cookie", expired_cookie_header(DRIVE_TOKEN_COOKIE, secure=is_secure_cookie()))
        self.send_header("Set-Cookie", expired_cookie_header(DRIVE_STATE_COOKIE, secure=is_secure_cookie()))
        self.end_headers()
