from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class ElevenLabsError(RuntimeError):
    """Raised when ElevenLabs text-to-speech generation fails."""


class ElevenLabsClient:
    base_url = "https://api.elevenlabs.io"

    def __init__(self, *, timeout: int = 60) -> None:
        self._timeout = timeout

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
        query = urlencode({"output_format": output_format})
        url = f"{self.base_url}/v1/text-to-speech/{quote(voice_id)}?{query}"
        body = json.dumps(
            {
                "text": text,
                "model_id": model_id,
                "language_code": language_code,
                "voice_settings": voice_settings,
            }
        ).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "content-type": "application/json",
                "accept": "audio/mpeg",
                "xi-api-key": api_key,
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self._timeout) as response:
                return response.read()
        except HTTPError as exc:
            raise ElevenLabsError(f"ElevenLabs request failed with status {exc.code}") from exc
        except URLError as exc:
            raise ElevenLabsError("ElevenLabs request failed") from exc
