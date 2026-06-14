from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote


DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_LANGUAGE_CODE = "fr"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_FILENAME = "french-audiobook"


class OutputDirectoryError(RuntimeError):
    """Raised when generated audio cannot be written to the output directory."""


class TtsClient(Protocol):
    def synthesize(
        self,
        *,
        api_key: str,
        voice_id: str,
        model_id: str,
        language_code: str,
        output_format: str,
        text: str,
        voice_settings: dict[str, float],
    ) -> bytes:
        ...


@dataclass(frozen=True)
class AudiobookConfig:
    api_key: str
    output_dir: Path
    default_voice_id: str
    default_model_id: str = DEFAULT_MODEL_ID
    language_code: str = DEFAULT_LANGUAGE_CODE
    output_format: str = DEFAULT_OUTPUT_FORMAT


@dataclass(frozen=True)
class GenerationResult:
    path: Path
    download_url: str
    segments: int


@dataclass(frozen=True)
class GeneratedAudio:
    audio: bytes
    filename: str
    segments: int


class AudiobookGenerator:
    def __init__(self, *, config: AudiobookConfig, tts_client: TtsClient) -> None:
        self._config = config
        self._tts_client = tts_client

    def generate(
        self,
        text: str,
        *,
        title: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        pause_ms: int = 500,
        voice_settings: dict[str, float] | None = None,
    ) -> GenerationResult:
        generated = self.generate_audio(
            text,
            title=title,
            voice_id=voice_id,
            model_id=model_id,
            pause_ms=pause_ms,
            voice_settings=voice_settings,
        )
        output_dir = self._validated_output_dir()
        filename = unique_mp3_path(output_dir, Path(generated.filename).stem)
        filename.write_bytes(generated.audio)
        return GenerationResult(
            path=filename,
            download_url=f"/downloads/{quote(filename.name)}",
            segments=generated.segments,
        )

    def generate_audio(
        self,
        text: str,
        *,
        title: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        pause_ms: int = 500,
        voice_settings: dict[str, float] | None = None,
    ) -> GeneratedAudio:
        segments = split_text_segments(text)
        if not segments:
            raise ValueError("French text is required.")

        filename = f"{slugify(title or segments[0])}.mp3"
        selected_voice_id = (voice_id or self._config.default_voice_id).strip()
        selected_model_id = (model_id or self._config.default_model_id).strip()

        audio_parts = [
            self._tts_client.synthesize(
                api_key=self._config.api_key,
                voice_id=selected_voice_id,
                model_id=selected_model_id,
                language_code=self._config.language_code,
                output_format=self._config.output_format,
                text=segment,
                voice_settings=voice_settings or {},
            )
            for segment in segments
        ]

        return GeneratedAudio(
            audio=join_audio_parts(audio_parts, pause_ms=pause_ms),
            filename=filename,
            segments=len(segments),
        )

    def _validated_output_dir(self) -> Path:
        output_dir = self._config.output_dir
        if not output_dir.exists() or not output_dir.is_dir():
            raise OutputDirectoryError("ONEDRIVE_AUDIO_DIR must be an existing directory.")
        return output_dir


def split_text_segments(text: str, *, max_chars: int = 4500) -> list[str]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", normalized)]
    chunks: list[str] = []
    for paragraph in [paragraph for paragraph in paragraphs if paragraph]:
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
            continue
        chunks.extend(_split_long_paragraph(paragraph, max_chars=max_chars))
    return chunks


def _split_long_paragraph(paragraph: str, *, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?;:])\s+", paragraph)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current = f"{current} {sentence}"
        else:
            chunks.append(current)
            current = sentence

        while len(current) > max_chars:
            chunks.append(current[:max_chars].strip())
            current = current[max_chars:].strip()

    if current:
        chunks.append(current)
    return chunks


def slugify(value: str) -> str:
    ascii_value = value.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug[:80].strip("-") or DEFAULT_FILENAME


def unique_mp3_path(output_dir: Path, slug: str) -> Path:
    path = output_dir / f"{slug}.mp3"
    index = 2
    while path.exists():
        path = output_dir / f"{slug}-{index}.mp3"
        index += 1
    return path


def join_audio_parts(parts: list[bytes], *, pause_ms: int) -> bytes:
    pause = b"" if pause_ms <= 0 else b"\n\n"
    return pause.join(parts)
