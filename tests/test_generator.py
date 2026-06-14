from pathlib import Path

import pytest

from french_audiobook.generator import (
    AudiobookConfig,
    AudiobookGenerator,
    OutputDirectoryError,
)


class FakeTtsClient:
    def __init__(self):
        self.calls = []

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        return f"audio:{kwargs['text']}".encode("utf-8")


def make_config(tmp_path: Path) -> AudiobookConfig:
    return AudiobookConfig(
        api_key="secret-key",
        output_dir=tmp_path,
        default_voice_id="voice-1",
        default_model_id="eleven_multilingual_v2",
    )


def test_generator_writes_mp3_and_returns_metadata(tmp_path):
    client = FakeTtsClient()
    generator = AudiobookGenerator(config=make_config(tmp_path), tts_client=client)

    result = generator.generate(
        "Bonjour.\n\nComment ca va?",
        title="Lecon 1: Salutations!",
        pause_ms=750,
        voice_settings={"stability": 0.5, "speed": 0.95},
    )

    assert result.path == tmp_path / "lecon-1-salutations.mp3"
    assert result.path.read_bytes() == b"audio:Bonjour.\n\naudio:Comment ca va?"
    assert result.download_url == "/downloads/lecon-1-salutations.mp3"
    assert result.segments == 2
    assert [call["text"] for call in client.calls] == ["Bonjour.", "Comment ca va?"]
    assert client.calls[0]["api_key"] == "secret-key"
    assert client.calls[0]["voice_id"] == "voice-1"
    assert client.calls[0]["model_id"] == "eleven_multilingual_v2"
    assert client.calls[0]["language_code"] == "fr"
    assert client.calls[0]["output_format"] == "mp3_44100_128"
    assert client.calls[0]["voice_settings"] == {"stability": 0.5, "speed": 0.95}


def test_generator_can_return_audio_without_persistent_storage(tmp_path):
    client = FakeTtsClient()
    missing_dir = tmp_path / "missing"
    config = AudiobookConfig(
        api_key="secret-key",
        output_dir=missing_dir,
        default_voice_id="voice-1",
        default_model_id="eleven_multilingual_v2",
    )
    generator = AudiobookGenerator(config=config, tts_client=client)

    result = generator.generate_audio(
        "Bonjour.\n\nComment ca va?",
        title="Lecon 1: Salutations!",
        pause_ms=750,
        voice_settings={"stability": 0.5},
    )

    assert result.filename == "lecon-1-salutations.mp3"
    assert result.audio == b"audio:Bonjour.\n\naudio:Comment ca va?"
    assert result.segments == 2
    assert not missing_dir.exists()


def test_generator_uses_custom_voice_and_model(tmp_path):
    client = FakeTtsClient()
    generator = AudiobookGenerator(config=make_config(tmp_path), tts_client=client)

    generator.generate(
        "Bonjour",
        title="Custom",
        voice_id="voice-2",
        model_id="model-2",
    )

    assert client.calls[0]["voice_id"] == "voice-2"
    assert client.calls[0]["model_id"] == "model-2"


def test_generator_rejects_empty_text(tmp_path):
    generator = AudiobookGenerator(config=make_config(tmp_path), tts_client=FakeTtsClient())

    with pytest.raises(ValueError, match="French text is required"):
        generator.generate("   ")


def test_generator_rejects_missing_output_directory(tmp_path):
    missing_dir = tmp_path / "missing"
    config = AudiobookConfig(
        api_key="secret-key",
        output_dir=missing_dir,
        default_voice_id="voice-1",
        default_model_id="eleven_multilingual_v2",
    )
    generator = AudiobookGenerator(config=config, tts_client=FakeTtsClient())

    with pytest.raises(OutputDirectoryError, match="ONEDRIVE_AUDIO_DIR"):
        generator.generate("Bonjour")
