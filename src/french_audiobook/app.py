from __future__ import annotations

import json
import os
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from french_audiobook.elevenlabs import ElevenLabsClient, ElevenLabsError
from french_audiobook.generator import (
    AudiobookConfig,
    AudiobookGenerator,
    DEFAULT_MODEL_ID,
    DEFAULT_VOICE_ID,
    GeneratedAudio,
    GenerationResult,
    OutputDirectoryError,
)
from french_audiobook.onedrive import (
    DRIVE_STATE_COOKIE,
    DRIVE_TOKEN_COOKIE,
    OneDriveConfig,
    OneDriveError,
    authorize_url,
    cookie_header,
    cookie_value_from_header,
    enabled_from_env,
    exchange_code_for_token,
    expired_cookie_header,
    is_secure_cookie,
    new_oauth_state,
    safe_drive_filename,
    signed_cookie_dumps,
    token_from_cookie_header,
    upload_mp3_to_onedrive,
    valid_access_token,
)


STATIC_DIR = Path(__file__).resolve().parents[2] / "dist"
ENV_FILE = Path.cwd() / ".env"
LOG_PREFIX = "[FrenchAudiobook]"


class AppConfigError(RuntimeError):
    """Raised when required app configuration is missing."""


@dataclass(frozen=True)
class AppSettings:
    config: AudiobookConfig
    onedrive: OneDriveConfig
    missing_required: tuple[str, ...] = ()


@dataclass(frozen=True)
class UploadedAudio:
    audio: bytes
    filename: str


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
    voice_id = values.get("ELEVENLABS_DEFAULT_VOICE_ID", DEFAULT_VOICE_ID).strip() or DEFAULT_VOICE_ID
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
        onedrive=enabled_from_env(values),
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
        "default_voice_id": settings.config.default_voice_id,
        "has_default_voice": bool(settings.config.default_voice_id),
        "storage_mode": "direct_response",
        "onedrive_enabled": settings.onedrive.enabled,
        "onedrive_folder_name": settings.onedrive.folder_name,
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


def build_onedrive_status_payload(settings: AppSettings, cookie_header_value: str | None) -> dict[str, bool]:
    return {
        "enabled": settings.onedrive.enabled,
        "connected": settings.onedrive.enabled
        and token_from_cookie_header(settings.onedrive, cookie_header_value) is not None,
    }


def parse_multipart_audio_upload(raw: bytes, content_type: str) -> UploadedAudio:
    if not content_type.lower().startswith("multipart/form-data"):
        raise ValueError("OneDrive save expects a generated MP3 upload.")

    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + raw
    )
    if not message.is_multipart():
        raise ValueError("OneDrive save expects multipart form data.")

    filename = ""
    audio = b""
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        field_name = part.get_param("name", header="content-disposition")
        if field_name == "filename":
            filename = part.get_content().strip()
        elif field_name == "audio":
            audio = part.get_payload(decode=True) or b""
            filename = filename or part.get_filename() or ""

    if not audio:
        raise ValueError("OneDrive save did not receive an MP3 file.")
    return UploadedAudio(audio=audio, filename=safe_drive_filename(filename))


def save_uploaded_audio_to_onedrive(
    audio: bytes,
    *,
    filename: str,
    settings: AppSettings,
    cookie_header_value: str | None,
    set_cookie: Any | None = None,
) -> dict[str, Any]:
    if not settings.onedrive.enabled:
        raise OneDriveError("OneDrive auth is not configured.", status=503)

    token = token_from_cookie_header(settings.onedrive, cookie_header_value)
    if not token:
        raise OneDriveError("OneDrive auth required.", status=401)

    access_token, refreshed_token = valid_access_token(settings.onedrive, token)
    safe_filename = safe_drive_filename(filename)
    uploaded = upload_mp3_to_onedrive(settings.onedrive, access_token, safe_filename, audio)

    if refreshed_token != token and set_cookie is not None:
        set_cookie(
            cookie_header(
                DRIVE_TOKEN_COOKIE,
                signed_cookie_dumps(refreshed_token, settings.onedrive.cookie_secret),
                max_age=60 * 60 * 24 * 21,
                secure=is_secure_cookie(),
            )
        )

    return {
        "id": uploaded.get("id"),
        "name": uploaded.get("name", safe_filename),
        "webViewLink": uploaded.get("webUrl"),
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
        parsed_path = urlparse(self.path)
        if parsed_path.path == "/api/auth/microsoft/logout":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Set-Cookie", expired_cookie_header(DRIVE_TOKEN_COOKIE, secure=is_secure_cookie()))
            self.send_header("Set-Cookie", expired_cookie_header(DRIVE_STATE_COOKIE, secure=is_secure_cookie()))
            self.end_headers()
            return

        if parsed_path.path == "/api/drive/save":
            self._handle_onedrive_save()
            return

        if parsed_path.path != "/api/generate":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            body = self._read_json_body()
            print(
                f"{LOG_PREFIX} /api/generate request "
                f"text_length={len(str(body.get('text', '')))} "
                f"title_provided={bool(str(body.get('title', '')).strip())} "
                f"voice_provided={bool(str(body.get('voice_id', '')).strip())}",
                flush=True,
            )
            result = generate_audio_from_body(body, settings=self._settings)
        except (ValueError, OutputDirectoryError, ElevenLabsError) as exc:
            print(f"{LOG_PREFIX} /api/generate rejected: {exc}", flush=True)
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except AppConfigError as exc:
            print(f"{LOG_PREFIX} /api/generate config error: {exc}", flush=True)
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        print(
            f"{LOG_PREFIX} /api/generate success "
            f"filename={result.filename} segments={result.segments} bytes={len(result.audio)}",
            flush=True,
        )
        self.send_response(HTTPStatus.CREATED)
        for key, value in audio_response_headers(result).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(result.audio)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            self._send_json(build_config_payload(self._settings), status=HTTPStatus.OK)
            return
        if parsed.path == "/api/auth/microsoft/status":
            self._send_json(
                build_onedrive_status_payload(self._settings, self.headers.get("cookie")),
                status=HTTPStatus.OK,
            )
            return
        if parsed.path == "/api/auth/microsoft/start":
            self._handle_microsoft_start()
            return
        if parsed.path == "/api/auth/microsoft/callback":
            self._handle_microsoft_callback(parsed.query)
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

    def _handle_microsoft_start(self) -> None:
        if not self._settings.onedrive.enabled:
            self._send_json({"error": "OneDrive auth is not configured."}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        state = new_oauth_state()
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", authorize_url(self._settings.onedrive, state=state))
        self.send_header(
            "Set-Cookie",
            cookie_header(DRIVE_STATE_COOKIE, state, max_age=600, secure=is_secure_cookie()),
        )
        self.end_headers()

    def _handle_microsoft_callback(self, query: str) -> None:
        if not self._settings.onedrive.enabled:
            self._send_json({"error": "OneDrive auth is not configured."}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        params = parse_qs(query)
        state = params.get("state", [""])[0]
        code = params.get("code", [""])[0]
        expected_state = cookie_value_from_header(self.headers.get("cookie"), DRIVE_STATE_COOKIE)
        if not state or not expected_state or state != expected_state:
            self._send_json({"error": "Invalid OAuth state."}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            token = exchange_code_for_token(self._settings.onedrive, code)
        except OneDriveError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus(exc.status))
            return

        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            cookie_header(
                DRIVE_TOKEN_COOKIE,
                signed_cookie_dumps(token, self._settings.onedrive.cookie_secret),
                max_age=60 * 60 * 24 * 21,
                secure=is_secure_cookie(),
            ),
        )
        self.send_header("Set-Cookie", expired_cookie_header(DRIVE_STATE_COOKIE, secure=is_secure_cookie()))
        self.end_headers()

    def _handle_onedrive_save(self) -> None:
        try:
            upload = self._read_audio_upload()
            print(
                f"{LOG_PREFIX} /api/drive/save request "
                f"filename={upload.filename} bytes={len(upload.audio)}",
                flush=True,
            )
            set_cookies: list[str] = []
            payload = save_uploaded_audio_to_onedrive(
                upload.audio,
                filename=upload.filename,
                settings=self._settings,
                cookie_header_value=self.headers.get("cookie"),
                set_cookie=set_cookies.append,
            )
        except (ValueError, OutputDirectoryError, ElevenLabsError, OneDriveError, AppConfigError) as exc:
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

    def _read_audio_upload(self) -> UploadedAudio:
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length)
        return parse_multipart_audio_upload(raw, self.headers.get("content-type", ""))

    def _send_json(
        self,
        payload: dict[str, Any],
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
