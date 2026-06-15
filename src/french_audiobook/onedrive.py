from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


MICROSOFT_SCOPES = "offline_access Files.ReadWrite"
MICROSOFT_GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
DRIVE_FOLDER_NAME = "French Audiobook MP3"
DRIVE_TOKEN_COOKIE = "onedrive_auth"
DRIVE_STATE_COOKIE = "onedrive_oauth_state"


class OneDriveError(RuntimeError):
    def __init__(self, message: str, *, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class OneDriveConfig:
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    cookie_secret: str = ""
    tenant: str = "consumers"
    folder_name: str = DRIVE_FOLDER_NAME

    @property
    def enabled(self) -> bool:
        return all((self.client_id, self.client_secret, self.redirect_uri, self.cookie_secret))


def enabled_from_env(env: dict[str, str] | None = None) -> OneDriveConfig:
    values = env or os.environ
    return OneDriveConfig(
        client_id=values.get("MICROSOFT_CLIENT_ID", "").strip(),
        client_secret=values.get("MICROSOFT_CLIENT_SECRET", "").strip(),
        redirect_uri=values.get("MICROSOFT_REDIRECT_URI", "").strip(),
        cookie_secret=values.get("OAUTH_COOKIE_SECRET", "").strip(),
        tenant=values.get("MICROSOFT_TENANT", "consumers").strip() or "consumers",
        folder_name=values.get("MICROSOFT_ONEDRIVE_FOLDER_NAME", DRIVE_FOLDER_NAME).strip() or DRIVE_FOLDER_NAME,
    )


def new_oauth_state() -> str:
    return secrets.token_urlsafe(24)


def authorize_url(config: OneDriveConfig, *, state: str) -> str:
    params = {
        "client_id": config.client_id,
        "response_type": "code",
        "redirect_uri": config.redirect_uri,
        "response_mode": "query",
        "scope": MICROSOFT_SCOPES,
        "state": state,
        "prompt": "select_account",
    }
    return f"{_login_root(config)}/authorize?{urlencode(params)}"


def exchange_code_for_token(config: OneDriveConfig, code: str) -> dict[str, Any]:
    return _request_token(
        config,
        {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
            "scope": MICROSOFT_SCOPES,
        },
    )


def valid_access_token(config: OneDriveConfig, token: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    access_token = str(token.get("access_token", ""))
    if access_token and int(token.get("expires_at", 0)) > int(time.time()):
        return access_token, token

    refresh_token = str(token.get("refresh_token", ""))
    if not refresh_token:
        raise OneDriveError("OneDrive auth expired. Reconnect required.", status=401)

    refreshed = _request_token(
        config,
        {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri": config.redirect_uri,
            "scope": MICROSOFT_SCOPES,
        },
    )
    if "refresh_token" not in refreshed:
        refreshed["refresh_token"] = refresh_token
    return str(refreshed["access_token"]), refreshed


def _request_token(config: OneDriveConfig, data: dict[str, str]) -> dict[str, Any]:
    body = urlencode(data).encode("utf-8")
    request = Request(
        f"{_login_root(config)}/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        response = urlopen(request, timeout=20)
        payload = _read_json_response(response)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise OneDriveError("OneDrive auth request failed.", status=502) from exc

    payload["expires_at"] = int(time.time()) + int(payload.get("expires_in", 3600)) - 60
    return payload


def upload_mp3_to_onedrive(
    config: OneDriveConfig,
    access_token: str,
    filename: str,
    mp3_data: bytes,
) -> dict[str, Any]:
    safe_filename = safe_drive_filename(filename)
    ensure_onedrive_folder(config, access_token)
    encoded_path = _drive_path(config.folder_name, safe_filename)
    request = Request(
        f"{MICROSOFT_GRAPH_ROOT}/me/drive/root:/{encoded_path}:/content",
        data=mp3_data,
        headers={**_graph_headers(access_token), "Content-Type": "audio/mpeg"},
        method="PUT",
    )
    try:
        response = urlopen(request, timeout=60)
        return _read_json_response(response)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise OneDriveError("OneDrive upload failed.", status=502) from exc


def ensure_onedrive_folder(config: OneDriveConfig, access_token: str) -> None:
    encoded_name = _drive_path(config.folder_name)
    try:
        _graph_json("GET", f"/me/drive/root:/{encoded_name}", access_token)
        return
    except OneDriveError as exc:
        if exc.status != 404:
            raise

    _graph_json(
        "POST",
        "/me/drive/root/children",
        access_token,
        json_body={
            "name": config.folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "rename",
        },
    )


def _graph_json(
    method: str,
    path: str,
    access_token: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = _graph_headers(access_token)
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(f"{MICROSOFT_GRAPH_ROOT}{path}", data=data, headers=headers, method=method)
    try:
        response = urlopen(request, timeout=30)
        return _read_json_response(response)
    except HTTPError as exc:
        if exc.code == 404:
            raise OneDriveError("OneDrive item not found.", status=404) from exc
        raise OneDriveError("OneDrive request failed.", status=502) from exc
    except (URLError, OSError, ValueError) as exc:
        raise OneDriveError("OneDrive request failed.", status=502) from exc


def safe_drive_filename(name: str) -> str:
    stem = Path(name or "").stem
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")[:54]
    return f"{slug or 'french-audiobook'}.mp3"


def signed_cookie_dumps(payload: dict[str, Any], secret: str) -> str:
    data = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _cookie_signature(data, secret)
    return f"{data}.{signature}"


def signed_cookie_loads(value: str, secret: str) -> dict[str, Any] | None:
    if not value or "." not in value:
        return None
    data, signature = value.rsplit(".", 1)
    expected = _cookie_signature(data, secret)
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        decoded = _b64url_decode(data)
        parsed = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def cookie_value_from_header(header: str | None, name: str) -> str | None:
    if not header:
        return None
    cookie = SimpleCookie()
    cookie.load(header)
    morsel = cookie.get(name)
    return morsel.value if morsel else None


def token_from_cookie_header(config: OneDriveConfig, cookie_header: str | None) -> dict[str, Any] | None:
    raw = cookie_value_from_header(cookie_header, DRIVE_TOKEN_COOKIE)
    if not raw or not config.cookie_secret:
        return None
    return signed_cookie_loads(raw, config.cookie_secret)


def cookie_header(
    name: str,
    value: str,
    *,
    max_age: int,
    secure: bool,
    path: str = "/",
    http_only: bool = True,
) -> str:
    cookie = SimpleCookie()
    cookie[name] = value
    cookie[name]["path"] = path
    cookie[name]["max-age"] = str(max_age)
    cookie[name]["samesite"] = "Lax"
    if secure:
        cookie[name]["secure"] = True
    if http_only:
        cookie[name]["httponly"] = True
    return cookie.output(header="").strip()


def expired_cookie_header(name: str, *, secure: bool) -> str:
    return cookie_header(name, "", max_age=0, secure=secure)


def is_secure_cookie(env: dict[str, str] | None = None) -> bool:
    values = env or os.environ
    return values.get("ENV", "").lower() == "production" or values.get("VERCEL") == "1"


def _login_root(config: OneDriveConfig) -> str:
    tenant = quote(config.tenant or "consumers", safe="")
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"


def _drive_path(*parts: str) -> str:
    return "/".join(quote(part.strip("/"), safe="") for part in parts if part)


def _graph_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _read_json_response(response: Any) -> dict[str, Any]:
    status = int(getattr(response, "status", getattr(response, "code", 200)))
    if status < 200 or status >= 300:
        raise ValueError(f"Unexpected HTTP status {status}")
    payload = json.loads(response.read().decode("utf-8") or "{}")
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    return payload


def _cookie_signature(data: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()
    return _b64url(digest)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
