from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from json import JSONDecodeError
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from french_audiobook.app import (
    AppConfigError,
    app_settings_from_env,
    parse_json_body,
    save_audio_to_onedrive_from_body,
)
from french_audiobook.elevenlabs import ElevenLabsError
from french_audiobook.onedrive import OneDriveError


LOG_PREFIX = "[FrenchAudiobook]"


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            body = parse_json_body(self.rfile.read(length))
            print(
                f"{LOG_PREFIX} /api/drive/save request "
                f"text_length={len(str(body.get('text', '')))} "
                f"filename={str(body.get('filename', ''))[:80]}",
                flush=True,
            )
            set_cookies: list[str] = []
            payload = save_audio_to_onedrive_from_body(
                body,
                settings=app_settings_from_env(),
                cookie_header_value=self.headers.get("cookie"),
                set_cookie=set_cookies.append,
            )
        except (ValueError, JSONDecodeError, ElevenLabsError, OneDriveError, AppConfigError) as exc:
            status = getattr(exc, "status", HTTPStatus.BAD_REQUEST)
            print(f"{LOG_PREFIX} /api/drive/save rejected: {exc}", flush=True)
            self._send_json({"error": str(exc)}, status=HTTPStatus(status))
            return

        print(
            f"{LOG_PREFIX} /api/drive/save success "
            f"name={payload.get('name')} linked={bool(payload.get('webViewLink'))}",
            flush=True,
        )
        self._send_json(payload, status=HTTPStatus.OK, set_cookies=set_cookies)

    def _send_json(
        self,
        payload: dict[str, object],
        *,
        status: HTTPStatus,
        set_cookies: list[str] | None = None,
    ) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        for value in set_cookies or []:
            self.send_header("Set-Cookie", value)
        self.end_headers()
        self.wfile.write(data)
