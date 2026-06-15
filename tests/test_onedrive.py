import json
import time
from urllib.error import HTTPError

import pytest

from french_audiobook.onedrive import (
    DRIVE_FOLDER_NAME,
    DRIVE_TOKEN_COOKIE,
    MICROSOFT_GRAPH_ROOT,
    OneDriveConfig,
    OneDriveError,
    authorize_url,
    cookie_value_from_header,
    enabled_from_env,
    safe_drive_filename,
    signed_cookie_dumps,
    signed_cookie_loads,
    upload_mp3_to_onedrive,
    valid_access_token,
)


def config(**overrides):
    values = {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "redirect_uri": "https://example.test/api/auth/microsoft/callback",
        "cookie_secret": "cookie-secret",
        "tenant": "consumers",
        "folder_name": DRIVE_FOLDER_NAME,
    }
    values.update(overrides)
    return OneDriveConfig(**values)


def test_enabled_from_env_requires_all_auth_values():
    assert enabled_from_env(
        {
            "MICROSOFT_CLIENT_ID": "client-id",
            "MICROSOFT_CLIENT_SECRET": "client-secret",
            "MICROSOFT_REDIRECT_URI": "https://example.test/callback",
            "OAUTH_COOKIE_SECRET": "cookie-secret",
        }
    ).enabled

    assert not enabled_from_env({"MICROSOFT_CLIENT_ID": "client-id"}).enabled


def test_authorize_url_uses_files_read_write_and_offline_access():
    url = authorize_url(config(), state="state-1")

    assert url.startswith("https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?")
    assert "client_id=client-id" in url
    assert "response_type=code" in url
    assert "state=state-1" in url
    assert "scope=offline_access+Files.ReadWrite" in url


def test_signed_cookie_roundtrip_and_rejects_tampering():
    encoded = signed_cookie_dumps({"access_token": "token"}, "cookie-secret")

    assert signed_cookie_loads(encoded, "cookie-secret") == {"access_token": "token"}
    assert signed_cookie_loads(f"{encoded}tampered", "cookie-secret") is None


def test_cookie_value_from_header_reads_named_cookie():
    encoded = signed_cookie_dumps({"access_token": "token"}, "cookie-secret")
    header = f"other=1; {DRIVE_TOKEN_COOKIE}={encoded}; theme=light"

    assert cookie_value_from_header(header, DRIVE_TOKEN_COOKIE) == encoded


def test_valid_access_token_refreshes_expired_token(monkeypatch):
    calls = []

    class Response:
        status = 200

        def read(self):
            return json.dumps({"access_token": "fresh", "expires_in": 3600}).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.data.decode("utf-8"), timeout))
        return Response()

    monkeypatch.setattr("french_audiobook.onedrive.urlopen", fake_urlopen)

    access_token, refreshed = valid_access_token(
        config(),
        {"access_token": "stale", "refresh_token": "refresh-me", "expires_at": int(time.time()) - 5},
    )

    assert access_token == "fresh"
    assert refreshed["refresh_token"] == "refresh-me"
    assert "grant_type=refresh_token" in calls[0][1]


def test_safe_drive_filename_keeps_mp3_extension_and_removes_path_parts():
    assert safe_drive_filename("../Lecon 1: Bonjour!.wav") == "lecon-1-bonjour.mp3"
    assert safe_drive_filename("") == "french-audiobook.mp3"


def test_upload_mp3_to_onedrive_creates_folder_then_uploads(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status, body):
            self.status = status
            self._body = body

        def read(self):
            return json.dumps(self._body).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append(
            {
                "method": request.get_method(),
                "url": request.full_url,
                "headers": dict(request.header_items()),
                "body": request.data,
                "timeout": timeout,
            }
        )
        if request.get_method() == "GET":
            raise HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)
        if request.get_method() == "POST":
            return Response(201, {"id": "folder-id"})
        return Response(201, {"id": "file-id", "name": "lesson.mp3", "webUrl": "https://onedrive/file"})

    monkeypatch.setattr("french_audiobook.onedrive.urlopen", fake_urlopen)

    uploaded = upload_mp3_to_onedrive(config(), "access-token", "Lesson.mp3", b"mp3")

    assert uploaded == {"id": "file-id", "name": "lesson.mp3", "webUrl": "https://onedrive/file"}
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"] == f"{MICROSOFT_GRAPH_ROOT}/me/drive/root:/French%20Audiobook%20MP3"
    assert calls[1]["method"] == "POST"
    assert calls[2]["method"] == "PUT"
    assert calls[2]["url"] == (
        f"{MICROSOFT_GRAPH_ROOT}/me/drive/root:/French%20Audiobook%20MP3/lesson.mp3:/content"
    )
    assert calls[2]["headers"]["Content-type"] == "audio/mpeg"
    assert calls[2]["body"] == b"mp3"


def test_upload_mp3_to_onedrive_raises_clear_error(monkeypatch):
    class Response:
        status = 500

        def read(self):
            return b"{}"

    monkeypatch.setattr("french_audiobook.onedrive.urlopen", lambda request, timeout: Response())

    with pytest.raises(OneDriveError, match="OneDrive request failed"):
        upload_mp3_to_onedrive(config(), "access-token", "lesson.mp3", b"mp3")
