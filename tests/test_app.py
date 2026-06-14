import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from french_audiobook.app import (
    app_settings_from_env,
    audio_response_headers,
    build_config_payload,
    build_generation_payload,
    generate_audio_from_body,
    load_env_file,
    missing_generation_config,
    resolve_download_path,
    _voice_settings_from_body,
)
from french_audiobook.elevenlabs import ElevenLabsClient, ElevenLabsError


def test_app_settings_require_secret_and_output_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setenv("ONEDRIVE_AUDIO_DIR", str(tmp_path))

    settings = app_settings_from_env()

    assert settings.missing_required == ("ELEVENLABS_API_KEY",)


def test_app_settings_load_defaults_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "secret-key")
    monkeypatch.setenv("ONEDRIVE_AUDIO_DIR", str(tmp_path))
    monkeypatch.setenv("ELEVENLABS_DEFAULT_VOICE_ID", "voice-1")

    settings = app_settings_from_env()

    assert settings.config.api_key == "secret-key"
    assert settings.config.output_dir == tmp_path
    assert settings.config.default_voice_id == "voice-1"
    assert settings.missing_required == ()


def test_app_settings_allow_server_start_without_local_config(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ONEDRIVE_AUDIO_DIR", raising=False)
    monkeypatch.delenv("ELEVENLABS_DEFAULT_VOICE_ID", raising=False)

    settings = app_settings_from_env()

    assert settings.missing_required == ("ELEVENLABS_API_KEY",)
    assert str(settings.config.output_dir) == "generated"
    assert settings.config.default_voice_id == "JBFqnCBsd6RMkjVDRZzb"


def test_missing_generation_config_uses_built_in_default_voice(tmp_path):
    settings = app_settings_from_env(
        {
            "ELEVENLABS_API_KEY": "secret-key",
            "ONEDRIVE_AUDIO_DIR": str(tmp_path),
            "ELEVENLABS_DEFAULT_VOICE_ID": "",
        }
    )

    assert missing_generation_config(settings, voice_id="voice-from-form") == []
    assert missing_generation_config(settings, voice_id=None) == []


def test_load_env_file_adds_missing_values_without_overwriting(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "ELEVENLABS_API_KEY=from-file",
                "ELEVENLABS_DEFAULT_VOICE_ID='voice-1'",
                "ONEDRIVE_AUDIO_DIR=/tmp/audio",
            ]
        ),
        encoding="utf-8",
    )
    env = {"ELEVENLABS_API_KEY": "already-set"}

    load_env_file(env_file, env)

    assert env["ELEVENLABS_API_KEY"] == "already-set"
    assert env["ELEVENLABS_DEFAULT_VOICE_ID"] == "voice-1"
    assert env["ONEDRIVE_AUDIO_DIR"] == "/tmp/audio"


def test_build_generation_payload_omits_api_key(tmp_path):
    result = SimpleNamespace(
        path=tmp_path / "lesson.mp3",
        download_url="/downloads/lesson.mp3",
        segments=2,
    )

    payload = build_generation_payload(result)

    assert payload == {
        "path": str(tmp_path / "lesson.mp3"),
        "download_url": "/downloads/lesson.mp3",
        "preview_url": "/downloads/lesson.mp3",
        "segments": 2,
    }


def test_build_config_payload_uses_direct_response_storage(tmp_path):
    settings = app_settings_from_env(
        {
            "ELEVENLABS_API_KEY": "secret-key",
            "ONEDRIVE_AUDIO_DIR": str(tmp_path),
            "ELEVENLABS_DEFAULT_VOICE_ID": "voice-1",
        }
    )

    assert build_config_payload(settings) == {
        "default_model_id": "eleven_multilingual_v2",
        "default_voice_id": "voice-1",
        "has_default_voice": True,
        "storage_mode": "direct_response",
        "missing_required": [],
    }


def test_generate_audio_from_body_returns_streamable_audio(tmp_path):
    class FakeTtsClient:
        def synthesize(self, **kwargs):
            return f"audio:{kwargs['text']}".encode("utf-8")

    settings = app_settings_from_env(
        {
            "ELEVENLABS_API_KEY": "secret-key",
            "ONEDRIVE_AUDIO_DIR": str(tmp_path / "missing"),
            "ELEVENLABS_DEFAULT_VOICE_ID": "voice-1",
        }
    )

    generated = generate_audio_from_body(
        {"text": "Bonjour.\n\nSalut.", "title": "Lecon", "pause_ms": 0},
        settings=settings,
        tts_client=FakeTtsClient(),
    )

    assert generated.audio == b"audio:Bonjour.audio:Salut."
    assert generated.filename == "lecon.mp3"
    assert generated.segments == 2
    assert audio_response_headers(generated) == {
        "content-type": "audio/mpeg",
        "content-length": "26",
        "content-disposition": 'attachment; filename="lecon.mp3"',
        "x-audiobook-segments": "2",
    }


def test_resolve_download_path_stays_inside_output_dir(tmp_path):
    audio = tmp_path / "lesson.mp3"
    audio.write_bytes(b"audio")

    assert resolve_download_path(tmp_path, "lesson.mp3") == audio

    with pytest.raises(FileNotFoundError):
        resolve_download_path(tmp_path, "../secret.env")


def test_voice_settings_validate_ranges():
    assert _voice_settings_from_body(
        {
            "stability": "0.4",
            "similarity_boost": "0.8",
            "style": "0",
            "speed": "1.1",
        }
    ) == {
        "stability": 0.4,
        "similarity_boost": 0.8,
        "style": 0,
        "speed": 1.1,
    }

    with pytest.raises(ValueError, match="speed must be between 0.7 and 1.2"):
        _voice_settings_from_body({"speed": "2"})


def test_elevenlabs_client_sends_expected_request(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"mp3"

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("french_audiobook.elevenlabs.urlopen", fake_urlopen)

    client = ElevenLabsClient()
    audio = client.synthesize(
        api_key="secret-key",
        voice_id="voice-1",
        model_id="eleven_multilingual_v2",
        language_code="fr",
        output_format="mp3_44100_128",
        text="Bonjour",
        voice_settings={"stability": 0.5},
    )

    assert audio == b"mp3"
    assert captured["url"].endswith("/v1/text-to-speech/voice-1?output_format=mp3_44100_128")
    assert captured["headers"]["Xi-api-key"] == "secret-key"
    assert captured["body"] == {
        "text": "Bonjour",
        "model_id": "eleven_multilingual_v2",
        "language_code": "fr",
        "voice_settings": {"stability": 0.5},
    }
    assert captured["timeout"] == 60


def test_elevenlabs_error_does_not_expose_api_key(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            401,
            "Unauthorized secret-key",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("french_audiobook.elevenlabs.urlopen", fake_urlopen)

    client = ElevenLabsClient()
    with pytest.raises(ElevenLabsError) as exc_info:
        client.synthesize(
            api_key="secret-key",
            voice_id="voice-1",
            model_id="eleven_multilingual_v2",
            language_code="fr",
            output_format="mp3_44100_128",
            text="Bonjour",
            voice_settings={},
        )

    assert "secret-key" not in str(exc_info.value)
