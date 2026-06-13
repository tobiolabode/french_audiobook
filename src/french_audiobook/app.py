from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from french_audiobook.elevenlabs import ElevenLabsClient, ElevenLabsError
from french_audiobook.generator import (
    AudiobookConfig,
    AudiobookGenerator,
    DEFAULT_MODEL_ID,
    GenerationResult,
    OutputDirectoryError,
)


STATIC_DIR = Path(__file__).with_name("static")
ENV_FILE = Path.cwd() / ".env"


class AppConfigError(RuntimeError):
    """Raised when required app configuration is missing."""


@dataclass(frozen=True)
class AppSettings:
    config: AudiobookConfig


def load_env_file(path: Path = ENV_FILE, env: dict[str, str] | None = None) -> None:
    target = env if env is not None else os.environ
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in target:
            target[key] = value


def app_settings_from_env(env: dict[str, str] | None = None) -> AppSettings:
    if env is None:
        load_env_file()
    values = env or os.environ
    api_key = values.get("ELEVENLABS_API_KEY", "").strip()
    output_dir = values.get("ONEDRIVE_AUDIO_DIR", "").strip()
    voice_id = values.get("ELEVENLABS_DEFAULT_VOICE_ID", "").strip()
    model_id = values.get("ELEVENLABS_DEFAULT_MODEL_ID", DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID

    missing = [
        name
        for name, value in {
            "ELEVENLABS_API_KEY": api_key,
            "ONEDRIVE_AUDIO_DIR": output_dir,
            "ELEVENLABS_DEFAULT_VOICE_ID": voice_id,
        }.items()
        if not value
    ]
    if missing:
        raise AppConfigError(f"Missing required environment variable: {', '.join(missing)}")

    return AppSettings(
        config=AudiobookConfig(
            api_key=api_key,
            output_dir=Path(output_dir),
            default_voice_id=voice_id,
            default_model_id=model_id,
        )
    )


def build_generation_payload(result: GenerationResult) -> dict[str, Any]:
    return {
        "path": str(result.path),
        "download_url": result.download_url,
        "preview_url": result.download_url,
        "segments": result.segments,
    }


def resolve_download_path(output_dir: Path, requested_name: str) -> Path:
    root = output_dir.resolve()
    candidate = (root / Path(requested_name).name).resolve()
    if candidate.parent != root or not candidate.is_file():
        raise FileNotFoundError(requested_name)
    return candidate


class FrenchAudiobookHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, settings: AppSettings, **kwargs: Any) -> None:
        self._settings = settings
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_POST(self) -> None:
        if self.path != "/api/generate":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            body = self._read_json_body()
            generator = AudiobookGenerator(
                config=self._settings.config,
                tts_client=ElevenLabsClient(),
            )
            result = generator.generate(
                body.get("text", ""),
                title=body.get("title"),
                voice_id=body.get("voice_id") or None,
                model_id=body.get("model_id") or None,
                pause_ms=_int_from_body(body, "pause_ms", 500),
                voice_settings=_voice_settings_from_body(body),
            )
        except (ValueError, OutputDirectoryError, ElevenLabsError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except AppConfigError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json(build_generation_payload(result), status=HTTPStatus.CREATED)

    def do_GET(self) -> None:
        if self.path == "/api/config":
            self._send_json(
                {
                    "default_model_id": self._settings.config.default_model_id,
                    "has_default_voice": bool(self._settings.config.default_voice_id),
                    "output_dir": str(self._settings.config.output_dir),
                },
                status=HTTPStatus.OK,
            )
            return
        if self.path.startswith("/downloads/"):
            self._serve_download(self.path.removeprefix("/downloads/"))
            return
        super().do_GET()

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Request body must be a JSON object.")
        return parsed

    def _serve_download(self, requested_name: str) -> None:
        try:
            path = resolve_download_path(self._settings.config.output_dir, requested_name)
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "audio/mpeg")
        self.send_header("content-length", str(path.stat().st_size))
        self.send_header("content-disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _int_from_body(body: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(body.get(key, default))
    except (TypeError, ValueError):
        return default


def _voice_settings_from_body(body: dict[str, Any]) -> dict[str, float]:
    settings = {}
    ranges = {
        "stability": ("stability", 0, 1),
        "similarity_boost": ("similarity_boost", 0, 1),
        "style": ("style", 0, 1),
        "speed": ("speed", 0.7, 1.2),
    }
    for source_key, (target_key, minimum, maximum) in ranges.items():
        value = body.get(source_key)
        if value in (None, ""):
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{source_key} must be a number.") from exc
        if parsed < minimum or parsed > maximum:
            raise ValueError(f"{source_key} must be between {minimum} and {maximum}.")
        settings[target_key] = parsed
    return settings


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    settings = app_settings_from_env()
    handler = partial(FrenchAudiobookHandler, settings=settings)
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = create_server(host, port)
    print(f"French Audiobook app running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
