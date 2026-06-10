"""
WebSocket service for Easy BDD Framework.

Maintains persistent connections via ConnectionPool so a session opened in one
step stays alive for subsequent steps.

YAML actions:
  websocket.connect  — open a WebSocket connection
  websocket.send     — send a message and optionally wait for a response
  websocket.receive  — receive the next message (no send)
  websocket.close    — close and evict the connection

Parameters shared across actions:
  url            — WebSocket URL (ws:// or wss://), required
  timeout        — seconds to wait for a response (default 10.0)
  headers        — dict of extra request headers (optional)
  store_as       — variable name to store the received message (optional)
  verify_ssl     — set false to skip TLS certificate verification (default true)

websocket.send parameters:
  data           — message to send; dict/list is JSON-serialised automatically
  method         — if set, wraps data in a JSON-RPC 2.0 envelope
  subprotocols   — list (or comma-separated string) of WebSocket subprotocols
  wait_for       — substring that must appear in a response before returning
  timeout        — how long to wait for the response (default 10.0)

Automatic token re-authentication:
  When the server closes the connection with an auth-related close code (4001,
  4003, 4401) or the connection/send raises an error containing "unauthorized",
  "forbidden", or "token", the service will:
    1. POST to auth_url with {"username": auth_username, "password": auth_password}
    2. Extract the new token from the response (looks for "token", "access_token",
       or "accessToken" keys at the top level or inside a "data" wrapper)
    3. Update the Authorization header with the new Bearer token
    4. Store the new token in the variable named by auth_token_var (default: "auth_token")
    5. Reconnect and retry the failed operation once

  Required params for reauth:
    auth_url       — HTTP(S) endpoint to POST credentials to (e.g. https://api.example.com/login)
    auth_username  — username / email
    auth_password  — password

  Optional:
    auth_token_var — variable name to store the refreshed token (default: "auth_token")
    auth_body_key  — JSON body field name for username if non-standard (default: "username")

Examples:
  steps:
    - websocket.connect:
        url: wss://firmware.testing.ovrc.com:10444
        subprotocols:
          - firmware-protocol
        headers:
          Authorization: "Bearer ${auth_token}"
        auth_url: https://api.ovrc.com/login
        auth_username: ${username}
        auth_password: ${password}

    - websocket.send:
        url: ${url}/dxUpdateFirmware
        method: dxUpdateFirmware
        subprotocols:
          - firmware-protocol
        data:
          deviceId: ${mac}
          version: 0
          url: ${upgrade_file}
        auth_url: https://api.ovrc.com/login
        auth_username: ${username}
        auth_password: ${password}
        store_as: update_response
"""

import json
import ssl
import threading
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ..core.connection_pool import ConnectionPool


def _pool_key(url: str) -> str:
    # Use the full URL as the key so different paths are separate connections
    return f"ws::{url}"


class _WSConn:
    """Synchronous WebSocket connection wrapper.

    Supports:
    - Optional subprotocols (e.g. ["firmware-protocol", session_id])
    - Optional extra headers (e.g. Origin, Authorization)
    - SSL with optional verification skip
    """

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 10.0,
        subprotocols: Optional[List[str]] = None,
        verify_ssl: bool = True,
    ):
        try:
            import websocket  # websocket-client
        except ImportError:
            raise ImportError(
                "websocket-client is required for websocket actions. "
                "Install it with: pip install websocket-client"
            )

        self._url = url
        self._timeout = timeout
        self._messages: List[str] = []
        self._lock = threading.Lock()
        self._connected = threading.Event()
        self._error: Optional[Exception] = None
        self._close_code: Optional[int] = None
        self._close_msg: str = ""

        # Build header list; add Origin if missing
        hdr = dict(headers or {})
        if "Origin" not in hdr and "origin" not in hdr:
            parsed = urlparse(url)
            scheme = "https" if parsed.scheme == "wss" else "http"
            hdr["Origin"] = f"{scheme}://{parsed.netloc}"
        header_list = [f"{k}: {v}" for k, v in hdr.items()]

        run_kwargs: Dict[str, Any] = {"ping_interval": 20, "ping_timeout": 10}
        if not verify_ssl and url.startswith("wss://"):
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            run_kwargs["sslopt"] = {"cert_reqs": ssl.CERT_NONE, "ssl_version": ssl.PROTOCOL_TLS}

        create_kwargs: Dict[str, Any] = {
            "header": header_list,
            "on_open": self._on_open,
            "on_message": self._on_message,
            "on_error": self._on_error,
            "on_close": self._on_close,
        }
        if subprotocols:
            create_kwargs["subprotocols"] = subprotocols

        self._ws = websocket.WebSocketApp(url, **create_kwargs)
        self._thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs=run_kwargs,
            daemon=True,
        )
        self._thread.start()
        if not self._connected.wait(timeout=timeout):
            self._ws.close()
            raise ConnectionError(f"WebSocket connection timed out: {url}")
        if self._error:
            raise self._error

    def _on_open(self, ws):
        self._connected.set()
        print(f"         ✅ WebSocket connected: {self._url}")

    def _on_message(self, ws, message):
        with self._lock:
            self._messages.append(message)

    def _on_error(self, ws, error):
        self._error = error
        print(f"         ⚠️  WebSocket error: {error}")
        self._connected.set()  # unblock the wait in __init__

    def _on_close(self, ws, close_status_code, close_msg):
        self._close_code = close_status_code
        self._close_msg = close_msg or ""
        if close_status_code:
            print(f"         🔒 WebSocket closed: code={close_status_code} msg={close_msg or ''}")

    def send(self, data: Any) -> None:
        if isinstance(data, (dict, list)):
            data = json.dumps(data)
        self._ws.send(data)

    def receive(self, timeout: float = 10.0, wait_for: Optional[str] = None) -> Optional[str]:
        """Return the next message, optionally waiting for one containing wait_for."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if wait_for:
                    for i, msg in enumerate(self._messages):
                        if wait_for in msg:
                            return self._messages.pop(i)
                elif self._messages:
                    return self._messages.pop(0)
            # Stop waiting if the connection has errored or the background thread died
            if self._error is not None or not self._thread.is_alive():
                break
            time.sleep(0.05)
        # Return any buffered message even if the connection dropped
        with self._lock:
            return self._messages.pop(0) if self._messages else ""

    def is_auth_error(self) -> bool:
        """Return True if the connection was closed with an auth-related code."""
        return self._close_code in (4001, 4003, 4401)

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass


# Auth-error signals in exception messages
_AUTH_SIGNALS = ("unauthorized", "forbidden", "token", "auth", "401", "403")


def _is_auth_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(sig in msg for sig in _AUTH_SIGNALS)


def _fetch_token(
    auth_url: str,
    auth_username: str,
    auth_password: str,
    auth_body_key: str = "username",
    verify_ssl: bool = True,
) -> str:
    """POST credentials to auth_url and return the bearer token."""
    import urllib.request
    import urllib.error
    import ssl as _ssl

    payload = json.dumps({
        auth_body_key: auth_username,
        "password": auth_password,
    }).encode()
    req = urllib.request.Request(
        auth_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ctx = None
    if not verify_ssl:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE

    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        body = json.loads(resp.read().decode())

    # Support {"token": "..."}, {"access_token": "..."}, {"data": {"token": ...}}
    for key in ("token", "access_token", "accessToken"):
        if key in body:
            return body[key]
    if isinstance(body.get("data"), dict):
        for key in ("token", "access_token", "accessToken"):
            if key in body["data"]:
                return body["data"][key]
    raise ValueError(
        f"Could not find token in auth response. Keys found: {list(body.keys())}"
    )


class WebSocketService:
    """Stateful WebSocket service backed by a shared ConnectionPool.

    Supports automatic token re-authentication: when a send/connect fails
    with an auth error (close code 4001/4003/4401 or an "unauthorized" /
    "forbidden" message), the service fetches a fresh token via auth_url,
    updates the Authorization header, evicts the stale connection, and
    retries once.
    """

    def __init__(self, pool: ConnectionPool):
        self._pool = pool
        # Shared reauth state across steps so we don't re-fetch mid-test
        # unless actually needed.  Keyed by auth_url.
        self._token_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Action dispatch                                                      #
    # ------------------------------------------------------------------ #

    def execute(self, action: str, params: Dict[str, Any], variables: Dict[str, Any]) -> Any:
        action_lower = action.lower()

        if "connect" in action_lower:
            return self._connect(params, variables)
        if "send" in action_lower:
            return self._send(params, variables)
        if "receive" in action_lower or "read" in action_lower:
            return self._receive(params, variables)
        if "close" in action_lower:
            return self._close(params)

        raise ValueError(f"Unknown websocket action: {action}")

    # ------------------------------------------------------------------ #
    # Reauth helpers                                                       #
    # ------------------------------------------------------------------ #

    def _reauth_params(self, params: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Return reauth config if all required fields are present, else None."""
        auth_url = params.get("auth_url", "")
        auth_username = params.get("auth_username", "")
        auth_password = params.get("auth_password", "")
        if auth_url and auth_username and auth_password:
            return {
                "auth_url": auth_url,
                "auth_username": auth_username,
                "auth_password": str(auth_password),
                "auth_body_key": params.get("auth_body_key", "username"),
                "auth_token_var": params.get("auth_token_var", "auth_token"),
                "verify_ssl": bool(params.get("verify_ssl", True)),
            }
        return None

    def _do_reauth(
        self,
        reauth: Dict[str, str],
        params: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> str:
        """Fetch a fresh token, update params headers + variables, return token."""
        print("      🔑 Auth error — fetching fresh token from", reauth["auth_url"])
        token = _fetch_token(
            auth_url=reauth["auth_url"],
            auth_username=reauth["auth_username"],
            auth_password=reauth["auth_password"],
            auth_body_key=reauth["auth_body_key"],
            verify_ssl=reauth["verify_ssl"],
        )
        # Update cached token
        self._token_cache[reauth["auth_url"]] = token

        # Patch the headers dict in-place so _make_conn uses the new token
        headers = params.setdefault("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        # Store in test variables so subsequent steps can use ${auth_token}
        token_var = reauth["auth_token_var"]
        variables[token_var] = token
        print(f"      ✅ Token refreshed — stored as '{token_var}'")
        return token

    # ------------------------------------------------------------------ #
    # Connection factory                                                   #
    # ------------------------------------------------------------------ #

    def _make_conn(self, url: str, params: Dict[str, Any]) -> "_WSConn":
        timeout = float(params.get("timeout", 10.0))
        headers = dict(params.get("headers") or {})
        verify_ssl = bool(params.get("verify_ssl", True))

        # Inject cached token if no Authorization header set yet
        auth_url = params.get("auth_url", "")
        if auth_url and "Authorization" not in headers and auth_url in self._token_cache:
            headers["Authorization"] = f"Bearer {self._token_cache[auth_url]}"

        raw_protos = params.get("subprotocols") or params.get("protocol") or []
        if isinstance(raw_protos, str):
            raw_protos = [p.strip() for p in raw_protos.split(",") if p.strip()]

        # Auto-append session UUID alongside named protocols
        if raw_protos and not any(_looks_like_uuid(p) for p in raw_protos):
            raw_protos = list(raw_protos) + [str(uuid.uuid4())]

        return _WSConn(url, headers, timeout, raw_protos or None, verify_ssl)

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _connect(self, params: Dict[str, Any], variables: Dict[str, Any]) -> bool:
        url = params.get("url", "")
        if not url:
            raise ValueError("websocket.connect requires 'url'")
        key = _pool_key(url)
        if self._pool.has(key):
            return True
        reauth = self._reauth_params(params)
        try:
            self._pool.acquire(key, lambda: self._make_conn(url, params))
        except Exception as exc:
            if reauth and _is_auth_error(exc):
                self._do_reauth(reauth, params, variables)
                self._pool.evict(key)
                self._pool.acquire(key, lambda: self._make_conn(url, params))
            else:
                raise
        return True

    def _send(self, params: Dict[str, Any], variables: Dict[str, Any]) -> str:
        url = params.get("url", "")
        data = params.get("data", "")
        timeout = float(params.get("timeout", 10.0))
        wait_for = params.get("wait_for") or None
        method = params.get("method") or None
        if not url:
            raise ValueError("websocket.send requires 'url'")

        reauth = self._reauth_params(params)

        def _build_payload():
            if method:
                return {
                    "jsonrpc": "2.0",
                    "method": method,
                    "id": str(uuid.uuid4()),
                    "params": data if isinstance(data, dict) else {},
                }
            return data

        def _attempt(conn: "_WSConn") -> str:
            conn.send(_build_payload())
            response = conn.receive(timeout=timeout, wait_for=wait_for)
            # Treat empty response on a connection that was auth-closed as an error
            if response == "" and conn.is_auth_error():
                raise ConnectionError("WebSocket closed with auth error")
            return response if response is not None else ""

        key = _pool_key(url)
        conn: _WSConn = self._pool.acquire(
            key, lambda: self._make_conn(url, params)
        )
        try:
            return _attempt(conn)
        except Exception as exc:
            self._pool.evict(key)
            if reauth and (_is_auth_error(exc) or (hasattr(conn, "is_auth_error") and conn.is_auth_error())):
                self._do_reauth(reauth, params, variables)
                new_conn = self._pool.acquire(key, lambda: self._make_conn(url, params))
                return _attempt(new_conn)
            raise

    def _receive(self, params: Dict[str, Any], variables: Dict[str, Any]) -> str:
        url = params.get("url", "")
        timeout = float(params.get("timeout", 10.0))
        wait_for = params.get("wait_for") or None
        if not url:
            raise ValueError("websocket.receive requires 'url'")
        key = _pool_key(url)
        reauth = self._reauth_params(params)
        conn: _WSConn = self._pool.acquire(
            key, lambda: self._make_conn(url, params)
        )
        try:
            response = conn.receive(timeout=timeout, wait_for=wait_for)
            if response == "" and conn.is_auth_error():
                raise ConnectionError("WebSocket closed with auth error")
            return response if response is not None else ""
        except Exception as exc:
            self._pool.evict(key)
            if reauth and _is_auth_error(exc):
                self._do_reauth(reauth, params, variables)
                new_conn = self._pool.acquire(key, lambda: self._make_conn(url, params))
                return new_conn.receive(timeout=timeout, wait_for=wait_for) or ""
            raise

    def _close(self, params: Dict[str, Any]) -> bool:
        url = params.get("url", "")
        if not url:
            return True
        self._pool.evict(_pool_key(url))
        return True


def _looks_like_uuid(s: str) -> bool:
    import re
    return bool(re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", s, re.I
    ))
