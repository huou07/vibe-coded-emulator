# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Google sign-in and Google Drive sync for Vibe Coded Emulator.

This module contains the parts that must be correct regardless of the web
framework: OAuth 2.0 Authorization Code + PKCE, token refresh, and a client for
the user's Drive *app data* area. It never stores or emits a client secret to a
client: the secret is server-only and optional (PKCE is the public-client path).

Design notes
------------
* Identity uses OpenID Connect (`openid email profile`).
* Emulator data uses `drive.appdata`, so the app can only ever touch files it
  created in its own hidden app-data folder. It cannot read the user's other
  Drive files.
* Only user-owned emulator data is uploaded. Firmware and key kinds are
  rejected by the mapper before any request is made.
* File identity is our own SHA-256, stored in Drive ``appProperties``, so hashes
  are comparable across devices instead of relying on Drive's MD5.

Network access goes through an injected transport, which keeps the module
unit-testable and keeps ``urllib`` usage in one place.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import sync_engine as se

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REVOKE_URI = "https://oauth2.googleapis.com/revoke"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"

IDENTITY_SCOPES = ("openid", "email", "profile")
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.appdata"
SYNC_SCOPES = IDENTITY_SCOPES + (DRIVE_SCOPE,)

# Files larger than this use Drive's resumable upload endpoint.
RESUMABLE_THRESHOLD = 5 * 1024 * 1024
CHUNK_SIZE = 8 * 1024 * 1024


class GoogleSyncError(RuntimeError):
    pass


class GoogleAuthError(GoogleSyncError):
    pass


@dataclass
class HttpResponse:
    status: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> dict:
        if not self.body:
            return {}
        try:
            return json.loads(self.body.decode("utf-8"))
        except ValueError as error:  # pragma: no cover - defensive
            raise GoogleSyncError("response was not valid JSON") from error


Transport = Callable[..., HttpResponse]


def urllib_transport(method: str, url: str, *, headers: Optional[Dict[str, str]] = None,
                     body: Optional[bytes] = None, timeout: float = 30.0) -> HttpResponse:
    """Default transport. Errors are returned as responses, not raised."""

    request = urllib.request.Request(url, data=body, method=method)
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResponse(response.status, dict(response.headers), response.read())
    except urllib.error.HTTPError as error:
        return HttpResponse(error.code, dict(error.headers or {}), error.read())


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------


def base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def create_pkce_pair() -> Tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` using S256."""

    verifier = base64url(secrets.token_bytes(64))
    challenge = base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


@dataclass(frozen=True)
class OAuthConfig:
    client_id: str
    redirect_uri: str
    client_secret: str = ""
    scopes: Sequence[str] = SYNC_SCOPES
    auth_uri: str = AUTH_URI
    token_uri: str = TOKEN_URI

    @property
    def is_confidential_client(self) -> bool:
        return bool(self.client_secret)


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str = ""
    expires_at: float = 0.0
    scope: str = ""
    token_type: str = "Bearer"

    @property
    def expired(self) -> bool:
        return self.expires_at > 0 and time.time() >= self.expires_at - 60

    def to_record(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "token_type": self.token_type,
        }

    @classmethod
    def from_record(cls, record: dict) -> "TokenSet":
        return cls(
            access_token=str(record.get("access_token") or ""),
            refresh_token=str(record.get("refresh_token") or ""),
            expires_at=float(record.get("expires_at") or 0.0),
            scope=str(record.get("scope") or ""),
            token_type=str(record.get("token_type") or "Bearer"),
        )


def authorization_url(config: OAuthConfig, *, state: str, code_challenge: str,
                      login_hint: str = "", prompt: str = "select_account") -> str:
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": " ".join(config.scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        # Without this Google only returns a refresh token on first consent.
        "prompt": f"consent {prompt}".strip(),
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{config.auth_uri}?{urllib.parse.urlencode(params)}"


def _token_request(config: OAuthConfig, payload: Dict[str, str], transport: Transport) -> TokenSet:
    payload = dict(payload)
    # PKCE public clients must not send a secret; confidential web clients may.
    if config.is_confidential_client:
        payload["client_secret"] = config.client_secret
    body = urllib.parse.urlencode(payload).encode("ascii")
    response = transport("POST", config.token_uri,
                         headers={"Content-Type": "application/x-www-form-urlencoded"},
                         body=body)
    data = response.json()
    if response.status != 200 or "access_token" not in data:
        raise GoogleAuthError(data.get("error_description") or data.get("error") or "token request failed")
    expires_in = float(data.get("expires_in") or 0)
    return TokenSet(
        access_token=str(data["access_token"]),
        refresh_token=str(data.get("refresh_token") or payload.get("refresh_token") or ""),
        expires_at=(time.time() + expires_in) if expires_in else 0.0,
        scope=str(data.get("scope") or ""),
        token_type=str(data.get("token_type") or "Bearer"),
    )


def exchange_code(config: OAuthConfig, *, code: str, code_verifier: str,
                  transport: Transport = urllib_transport) -> TokenSet:
    return _token_request(config, {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "code_verifier": code_verifier,
    }, transport)


def refresh_access_token(config: OAuthConfig, *, refresh_token: str,
                         transport: Transport = urllib_transport) -> TokenSet:
    if not refresh_token:
        raise GoogleAuthError("no refresh token is stored")
    return _token_request(config, {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": config.client_id,
    }, transport)


def revoke_token(token: str, *, transport: Transport = urllib_transport) -> None:
    body = urllib.parse.urlencode({"token": token}).encode("ascii")
    transport("POST", REVOKE_URI,
              headers={"Content-Type": "application/x-www-form-urlencoded"}, body=body)


def decode_id_token_claims(id_token: str) -> dict:
    """Read claims from an ID token.

    Signature verification is intentionally not done here: the token is only
    ever consumed after a server-side ``code`` exchange over TLS directly with
    Google, which is the OIDC-validated path. Callers must not accept an ID
    token that did not come from ``exchange_code``.
    """

    parts = id_token.split(".")
    if len(parts) != 3:
        raise GoogleAuthError("malformed id_token")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (ValueError, TypeError) as error:
        raise GoogleAuthError("unreadable id_token claims") from error


# ---------------------------------------------------------------------------
# Drive (app-data folder only)
# ---------------------------------------------------------------------------


class GoogleDriveClient:
    """Minimal Drive v3 client restricted to the app data folder."""

    def __init__(self, access_token: str, *, transport: Transport = urllib_transport):
        if not access_token:
            raise GoogleAuthError("an access token is required")
        self.access_token = access_token
        self.transport = transport

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        headers.update(extra or {})
        return headers

    def list_app_files(self, page_token: str = "") -> Tuple[List[dict], str]:
        query = urllib.parse.urlencode({
            "spaces": "appDataFolder",
            "fields": "nextPageToken,files(id,name,size,modifiedTime,md5Checksum,appProperties)",
            "pageSize": "1000",
            **({"pageToken": page_token} if page_token else {}),
        })
        response = self.transport("GET", f"{DRIVE_API}/files?{query}", headers=self._headers())
        data = response.json()
        if response.status != 200:
            raise GoogleSyncError(data.get("error", {}).get("message") or "Drive list failed")
        return data.get("files", []), data.get("nextPageToken", "")

    def upload(self, name: str, data: bytes, *, sha256: str,
               mime_type: str = "application/octet-stream", app_folder: bool = True) -> dict:
        metadata = {
            "name": name,
            "appProperties": {"sha256": sha256},
        }
        if app_folder:
            metadata["parents"] = ["appDataFolder"]
        if len(data) <= RESUMABLE_THRESHOLD:
            boundary = "vibe" + secrets.token_hex(16)
            body = self._multipart(boundary, metadata, data, mime_type)
            response = self.transport(
                "POST",
                f"{DRIVE_UPLOAD_API}/files?uploadType=multipart&fields=id,name,size,modifiedTime,appProperties",
                headers=self._headers({"Content-Type": f"multipart/related; boundary={boundary}"}),
                body=body,
            )
        else:
            response = self._resumable_upload(metadata, data, mime_type)
        result = response.json()
        if response.status not in (200, 201):
            raise GoogleSyncError(result.get("error", {}).get("message") or "Drive upload failed")
        return result

    def _multipart(self, boundary: str, metadata: dict, data: bytes, mime_type: str) -> bytes:
        head = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode("ascii")
        return head + data + tail

    def _resumable_upload(self, metadata: dict, data: bytes, mime_type: str) -> HttpResponse:
        start = self.transport(
            "POST",
            f"{DRIVE_UPLOAD_API}/files?uploadType=resumable&fields=id,name,size,modifiedTime,appProperties",
            headers=self._headers({"Content-Type": "application/json; charset=UTF-8",
                                   "X-Upload-Content-Type": mime_type,
                                   "X-Upload-Content-Length": str(len(data))}),
            body=json.dumps(metadata).encode("utf-8"),
        )
        if start.status not in (200, 201):
            raise GoogleSyncError("Drive resumable upload could not start")
        location = start.headers.get("Location") or start.headers.get("location")
        if not location:
            raise GoogleSyncError("Drive resumable upload returned no session URL")
        # Upload in bounded chunks so an interrupted transfer can resume.
        offset = 0
        response = HttpResponse(0)
        while offset < len(data):
            chunk = data[offset:offset + CHUNK_SIZE]
            last = offset + len(chunk) >= len(data)
            content_range = f"bytes {offset}-{offset + len(chunk) - 1}/{len(data)}"
            response = self.transport("PUT", location, headers=self._headers({
                "Content-Type": mime_type,
                "Content-Range": content_range,
            }), body=chunk)
            if response.status not in (200, 201, 308):
                raise GoogleSyncError("Drive resumable upload chunk failed")
            offset += len(chunk)
            if last:
                break
        return response

    def download(self, file_id: str) -> bytes:
        response = self.transport("GET", f"{DRIVE_API}/files/{urllib.parse.quote(file_id)}?alt=media",
                                  headers=self._headers())
        if response.status != 200:
            raise GoogleSyncError("Drive download failed")
        return response.body

    def delete(self, file_id: str) -> None:
        response = self.transport("DELETE", f"{DRIVE_API}/files/{urllib.parse.quote(file_id)}",
                                  headers=self._headers())
        if response.status not in (200, 204):
            raise GoogleSyncError("Drive delete failed")


# ---------------------------------------------------------------------------
# Mapping Drive + local into the shared sync engine
# ---------------------------------------------------------------------------


def _kind_for_name(name: str) -> se.ItemKind:
    lower = name.lower()
    if lower.endswith((".gba", ".nds", ".3ds", ".zip", ".gb", ".gbc", ".cue", ".iso", ".bin")):
        return se.ItemKind.ROM
    if lower.endswith(".state"):
        return se.ItemKind.STATE
    if lower.endswith((".sav", ".srm", ".dsv", ".rtc")):
        return se.ItemKind.SAVE
    if lower.endswith(".json"):
        return se.ItemKind.METADATA
    return se.ItemKind.METADATA


def drive_file_to_entry(file_meta: dict, local: Optional[se.ItemVersion]) -> se.SyncEntry:
    name = str(file_meta.get("name") or "")
    props = file_meta.get("appProperties") or {}
    remote = se.ItemVersion(
        content_hash=str(props.get("sha256") or file_meta.get("md5Checksum") or ""),
        size=int(file_meta.get("size") or 0),
        content_id=str(file_meta.get("id") or ""),
    )
    return se.SyncEntry(kind=_kind_for_name(name), key=name, local=local, remote=remote)


def build_drive_sync_entries(
    drive_files: Sequence[dict],
    local_versions: Dict[str, se.ItemVersion],
    last_synced: Optional[Dict[str, str]] = None,
) -> List[se.SyncEntry]:
    """Merge a Drive listing and the local index into sync-engine entries."""

    last_synced = last_synced or {}
    entries: List[se.SyncEntry] = []
    seen = set()
    for file_meta in drive_files:
        entry = drive_file_to_entry(file_meta, local_versions.get(str(file_meta.get("name"))))
        seen.add(entry.key)
        entries.append(se.SyncEntry(
            kind=entry.kind,
            key=entry.key,
            local=entry.local,
            remote=entry.remote,
            last_synced_hash=last_synced.get(entry.key, ""),
        ))
    for name, version in local_versions.items():
        if name in seen:
            continue
        entries.append(se.SyncEntry(kind=_kind_for_name(name), key=name, local=version,
                                    last_synced_hash=last_synced.get(name, "")))
    return entries


def is_upload_allowed(name: str) -> bool:
    """Guard for the last moment before a network request."""

    return se.is_sync_eligible(_kind_for_name(name))
