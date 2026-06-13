from pathlib import Path

import pytest

from french_audiobook.generator import (
    AudiobookConfig,
    AudiobookGenerator,
    GenerationError,
    OutputDirectoryError,
    sanitize_title,
)


class RecordingTtsClient:
    def __init__(self, chunks: list[bytes] | None = None):
        self.calls = []
        self._chunks = chunks or [b"segment-a", b"segment-b"]

    def synthesize(self, **request):
        self.calls.append(request)
        return self._chunks[len(self.calls) - 1]


def test_rejects_empty_text(tmp_path):
    generator = AudiobookGenerator(
        config=AudiobookConfig(
            api_key="secret-key",
            output_dir=tmp_path,
            default_voice_id="voice-1",
        ),
        tts_client=RecordingTtsClient(),
    )

    with pytest.raises(ValueError, match="text is required"):
        generator.generate("   \n\t")


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Lecon 1: cafe creme!", "lecon-1-cafe-creme"),
        ("  ***  ", "french-audiobook"),
        ("Tres_long_" * 20, ("tres-long-" * 8).rstrip("-")),
    ],
)
def test_sanitizes_output_titles(title, expected):
    assert sanitize_title(title) == expected


def test_requires_configured_writable_output_directory(tmp_path):
    missing_dir = tmp_path / "missing"
    generator = AudiobookGenerator(
        config=AudiobookConfig(
            api_key="secret-key",
            output_dir=missing_dir,
            default_voice_id="voice-1",
        ),
        tts_client=RecordingTtsClient(),
    )

    with pytest.raises(OutputDirectoryError, match="does not exist"):
        generator.generate("Bonjour")


def test_saves_generated_audio_in_configured_output_directory(tmp_path):
    client = RecordingTtsClient(chunks=[b"one", b"two"])
    generator = AudiobookGenerator(
        config=AudiobookConfig(
            api_key="secret-key",
            output_dir=tmp_path,
            default_voice_id="voice-1",
        ),
        tts_client=client,
        clock=lambda: "20260612-091500",
    )

    result = generator.generate(
        "Bonjour\n\nComment ca va?",
        title="Lecon 1: cafe creme!",
        pause_ms=750,
    )

    assert result.path == tmp_path / "20260612-091500-lecon-1-cafe-creme.mp3"
    assert result.path.read_bytes() == b"one" + b"\0" * 750 + b"two"
    assert result.download_url == "/downloads/20260612-091500-lecon-1-cafe-creme.mp3"
    assert result.segments == 2


def test_fails_clearly_when_output_save_cannot_complete(tmp_path):
    blocked_path = tmp_path / "not-a-directory"
    blocked_path.write_text("already here")
    generator = AudiobookGenerator(
        config=AudiobookConfig(
            api_key="secret-key",
            output_dir=blocked_path,
            default_voice_id="voice-1",
        ),
        tts_client=RecordingTtsClient(),
    )

    with pytest.raises(OutputDirectoryError, match="not a directory"):
        generator.generate("Bonjour")


def test_never_returns_api_key_in_metadata(tmp_path):
    generator = AudiobookGenerator(
        config=AudiobookConfig(
            api_key="super-secret-api-key",
            output_dir=tmp_path,
            default_voice_id="voice-1",
        ),
        tts_client=RecordingTtsClient(chunks=[b"audio"]),
        clock=lambda: "20260612-091500",
    )

    result = generator.generate("Bonjour", title="Secret test")

    assert "super-secret-api-key" not in repr(result)
    assert "super-secret-api-key" not in result.model_dump_json()


def test_mocked_elevenlabs_request_shape(tmp_path):
    client = RecordingTtsClient(chunks=[b"audio"])
    generator = AudiobookGenerator(
        config=AudiobookConfig(
            api_key="secret-key",
            output_dir=tmp_path,
            default_voice_id="default-voice",
            default_model_id="eleven_multilingual_v2",
        ),
        tts_client=client,
        clock=lambda: "20260612-091500",
    )

    generator.generate(
        "Bonjour",
        voice_id="override-voice",
        model_id="override-model",
        voice_settings={"stability": 0.4, "similarity_boost": 0.8},
    )

    assert client.calls == [
        {
            "api_key": "secret-key",
            "voice_id": "override-voice",
            "model_id": "override-model",
            "language_code": "fr",
            "output_format": "mp3_44100_128",
            "text": "Bonjour",
            "voice_settings": {"stability": 0.4, "similarity_boost": 0.8},
        }
    ]
