from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from french_audiobook.app import (
    AppConfigError,
    app_settings_from_env,
    audio_response_headers,
    generate_audio_from_body,
    parse_json_body,
)
from french_audiobook.elevenlabs import ElevenLabsError


LOG_PREFIX = "[FrenchAudiobook]"


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            body = parse_json_body(self.rfile.read(length))
            print(
                f"{LOG_PREFIX} /api/generate request "
                f"text_length={len(str(body.get('text', '')))} "
                f"title_provided={bool(str(body.get('title', '')).strip())} "
                f"voice_provided={bool(str(body.get('voice_id', '')).strip())}",
                flush=True,
            )
            generated = generate_audio_from_body(body, settings=app_settings_from_env())
        except (ValueError, ElevenLabsError) as exc:
            print(f"{LOG_PREFIX} /api/generate rejected: {exc}", flush=True)
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except AppConfigError as exc:
            print(f"{LOG_PREFIX} /api/generate config error: {exc}", flush=True)
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        print(
            f"{LOG_PREFIX} /api/generate success "
            f"filename={generated.filename} segments={generated.segments} bytes={len(generated.audio)}",
            flush=True,
        )
        self.send_response(HTTPStatus.CREATED)
        for key, value in audio_response_headers(generated).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(generated.audio)

    def _send_json(self, payload: dict[str, str], *, status: HTTPStatus) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
