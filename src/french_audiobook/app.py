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
    GeneratedAudio,
    GenerationResult,
    OutputDirectoryError,
)


STATIC_DIR = Path(__file__).resolve().parents[2] / "dist"
ENV_FILE = Path.cwd() / ".env"


class AppConfigError(RuntimeError):
    """Raised when required app configuration is missing."""


@dataclass(frozen=True)
class AppSettings:
    config: AudiobookConfig
    missing_required: tuple[str, ...] = ()


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
    output_dir_value = values.get("ONEDRIVE_AUDIO_DIR", "").strip() or "generated"
    voice_id = values.get("ELEVENLABS_DEFAULT_VOICE_ID", "").strip()
    model_id = values.get("ELEVENLABS_DEFAULT_MODEL_ID", DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID

    missing = [
        name
        for name, value in {
            "ELEVENLABS_API_KEY": api_key,
        }.items()
        if not value
    ]

    return AppSettings(
        config=AudiobookConfig(
            api_key=api_key,
            output_dir=Path(output_dir_value),
            default_voice_id=voice_id,
            default_model_id=model_id,
        ),
        missing_required=tuple(missing),
    )


def build_generation_payload(result: GenerationResult) -> dict[str, Any]:
    return {
        "path": str(result.path),
        "download_url": result.download_url,
        "preview_url": result.download_url,
        "segments": result.segments,
    }


def missing_generation_config(settings: AppSettings, *, voice_id: str | None = None) -> list[str]:
    missing = list(settings.missing_required)
    if not (voice_id or settings.config.default_voice_id).strip():
        missing.append("ELEVENLABS_DEFAULT_VOICE_ID or voice_id")
    return missing


def build_config_payload(settings: AppSettings) -> dict[str, Any]:
    return {
        "default_model_id": settings.config.default_model_id,
        "has_default_voice": bool(settings.config.default_voice_id),
        "storage_mode": "direct_response",
        "missing_required": list(settings.missing_required),
    }


def parse_json_body(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Request body must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object.")
    return parsed


def generate_audio_from_body(
    body: dict[str, Any],
    *,
    settings: AppSettings,
    tts_client: ElevenLabsClient | None = None,
) -> GeneratedAudio:
    missing = missing_generation_config(settings, voice_id=body.get("voice_id") or None)
    if missing:
        raise AppConfigError(f"Missing required configuration: {', '.join(missing)}")

    generator = AudiobookGenerator(
        config=settings.config,
        tts_client=tts_client or ElevenLabsClient(),
    )
    return generator.generate_audio(
        body.get("text", ""),
        title=body.get("title"),
        voice_id=body.get("voice_id") or None,
        model_id=body.get("model_id") or None,
        pause_ms=_int_from_body(body, "pause_ms", 500),
        voice_settings=_voice_settings_from_body(body),
    )


def audio_response_headers(generated: GeneratedAudio) -> dict[str, str]:
    safe_filename = generated.filename.replace('"', "")
    return {
        "content-type": "audio/mpeg",
        "content-length": str(len(generated.audio)),
        "content-disposition": f'attachment; filename="{safe_filename}"',
        "x-audiobook-segments": str(generated.segments),
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
            result = generate_audio_from_body(body, settings=self._settings)
        except (ValueError, OutputDirectoryError, ElevenLabsError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except AppConfigError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self.send_response(HTTPStatus.CREATED)
        for key, value in audio_response_headers(result).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(result.audio)

    def do_GET(self) -> None:
        if self.path == "/api/config":
            self._send_json(build_config_payload(self._settings), status=HTTPStatus.OK)
            return
        super().do_GET()

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length)
        return parse_json_body(raw)

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
