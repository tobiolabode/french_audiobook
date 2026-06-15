from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from french_audiobook.app import app_settings_from_env, build_onedrive_status_payload


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        payload = build_onedrive_status_payload(app_settings_from_env(), self.headers.get("cookie"))
        data = json.dumps(payload).encode("utf-8")

        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
