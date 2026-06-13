from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol


DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_TITLE = "french-audiobook"
MAX_TITLE_LENGTH = 80


class GenerationError(RuntimeError):
    """Base error for audiobook generation failures."""


class OutputDirectoryError(GenerationError):
    """Raised when audio cannot be saved to the configured output directory."""


@dataclass(frozen=True)
class AudiobookConfig:
    api_key: str
    output_dir: Path
    default_voice_id: str
    default_model_id: str = DEFAULT_MODEL_ID
    output_format: str = DEFAULT_OUTPUT_FORMAT


@dataclass(frozen=True)
class GenerationResult:
    path: Path
    download_url: str
    segments: int

    def model_dump_json(self) -> str:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return json.dumps(payload)


class TtsClient(Protocol):
    def synthesize(self, **request: object) -> bytes:
        """Return an MP3 byte chunk for the supplied ElevenLabs-style request."""


def sanitize_title(title: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", title or "")
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_title.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug:
        return DEFAULT_TITLE
    return slug[:MAX_TITLE_LENGTH].rstrip("-")


class AudiobookGenerator:
    def __init__(
        self,
        *,
        config: AudiobookConfig,
        tts_client: TtsClient,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._config = config
        self._tts_client = tts_client
        self._clock = clock or (lambda: datetime.now().strftime("%Y%m%d-%H%M%S"))

    def generate(
        self,
        text: str,
        *,
        title: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        voice_settings: dict[str, float] | None = None,
        pause_ms: int = 500,
    ) -> GenerationResult:
        segments = [line.strip() for line in text.splitlines() if line.strip()]
        if not segments:
            raise ValueError("text is required")

        output_dir = self._require_output_dir()
        chunks = [
            self._tts_client.synthesize(
                api_key=self._config.api_key,
                voice_id=voice_id or self._config.default_voice_id,
                model_id=model_id or self._config.default_model_id,
                language_code="fr",
                output_format=self._config.output_format,
                text=segment,
                voice_settings=voice_settings or {},
            )
            for segment in segments
        ]

        file_name = f"{self._clock()}-{sanitize_title(title)}.mp3"
        path = output_dir / file_name
        try:
            path.write_bytes(self._combine_chunks(chunks, pause_ms=pause_ms))
        except OSError as exc:
            raise OutputDirectoryError(f"could not save generated audio: {exc}") from exc

        return GenerationResult(
            path=path,
            download_url=f"/downloads/{file_name}",
            segments=len(segments),
        )

    def _require_output_dir(self) -> Path:
        output_dir = Path(self._config.output_dir)
        if not output_dir.exists():
            raise OutputDirectoryError(f"output directory does not exist: {output_dir}")
        if not output_dir.is_dir():
            raise OutputDirectoryError(f"output path is not a directory: {output_dir}")
        probe = output_dir / ".write-test"
        try:
            probe.write_bytes(b"")
            probe.unlink()
        except OSError as exc:
            raise OutputDirectoryError(f"output directory is not writable: {output_dir}") from exc
        return output_dir

    @staticmethod
    def _combine_chunks(chunks: list[bytes], *, pause_ms: int) -> bytes:
        silence = b"\0" * max(pause_ms, 0)
        return silence.join(chunks)
