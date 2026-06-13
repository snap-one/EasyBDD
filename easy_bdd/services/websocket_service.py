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
  verify_ssl     — set false to skip TLS certificate verification (default true).
                   Also read from test variables: ovrc_verify_ssl, ws_verify_ssl, verify_ssl.
                   For firmware.testing.ovrc.com set verify_ssl: false (testing cert).

websocket.send parameters:
  data           — message to send; dict/list is JSON-serialised automatically
  method         — if set, wraps data in a JSON-RPC 2.0 envelope
  subprotocols   — list (or comma-separated string) of WebSocket subprotocols
  wait_for       — substring that must appear in a response before returning
  timeout        — how long to wait for the response (default 10.0)

Automatic token re-authentication:
  When the server closes the connection with an auth-related close code (4001,
  4003, 4401), raises an error containing "unauthorized"/"forbidden"/"token", OR
  the response body contains "401"/"403"/"Unauthorized"/"Session Timeout" (OVRC
  returns auth errors as JSON text, not WebSocket close frames), the service will:
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
import time
import uuid
from typing import Any, Dict, List, Optional
from ..core.connection_pool import ConnectionPool

# Params that belong to the websocket action itself — not forwarded as JSON-RPC data
_WEBSOCKET_CONTROL_PARAMS = frozenset({
    "url", "method", "timeout", "wait_for", "data", "subprotocols", "protocol",
    "headers", "store_as", "verify_ssl", "session_token",
    "auth_url", "auth_username", "auth_password", "auth_body_key", "auth_token_var",
})


def _pool_key(url: str) -> str:
    # Use the full URL as the key so different paths are separate connections
    return f"ws::{url}"


class _WSConn:
    """Synchronous WebSocket connection using websocket.WebSocket (blocking recv).

    Using the synchronous API ensures that when the server sends a response
    frame and immediately closes the TCP connection, recv() returns the
    response frame before raising the close exception — eliminating the race
    condition that exists with the async WebSocketApp callback approach.
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
        self._close_code: Optional[int] = None
        self._closed: bool = False
        # Session identity — populated by _make_conn
        self._session_uuid: str = str(uuid.uuid4())
        self._msg_counter: int = 0

        # Build header dict — do NOT auto-inject Origin.
        # bdd's execute_websocket never adds Origin and OVRC servers work without it;
        # adding Origin can cause the server to silently close after the first message.
        hdr = dict(headers or {})

        # Inject subprotocols as a raw Sec-WebSocket-Protocol header rather than using
        # websocket-client's subprotocols= parameter.  The parameter path triggers
        # server-response validation in websocket-client which can conflict with how
        # OVRC echos (or doesn't echo) the protocol list.  Passing the header directly
        # matches bdd's execute_webservice approach exactly.
        if subprotocols:
            hdr["Sec-WebSocket-Protocol"] = ", ".join(subprotocols)

        sslopt: Dict[str, Any] = {}
        if not verify_ssl and url.startswith("wss://"):
            sslopt = {"cert_reqs": ssl.CERT_NONE}

        self._ws = websocket.WebSocket(sslopt=sslopt)
        self._ws.settimeout(timeout)
        self._ws.connect(url, header=hdr)
        print(f"         ✅ WebSocket connected: {url}")
        if subprotocols:
            print(f"         subprotocols: {subprotocols}")

    def send(self, data: Any) -> None:
        # Use compact JSON (no spaces) — matches bdd's json.dumps(separators=(',', ':'))
        if isinstance(data, (dict, list)):
            data = json.dumps(data, separators=(",", ":"))
        try:
            self._ws.send(data)
        except Exception:
            self._closed = True
            raise

    def receive(self, timeout: float = 10.0, wait_for: Optional[str] = None) -> str:
        """Return the next message.

        Uses a blocking recv() with settimeout so the frame that arrives
        just before the server closes is always returned correctly.
        Collects frames until wait_for is satisfied (or timeout).
        """
        import websocket

        self._ws.settimeout(timeout)
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            self._ws.settimeout(remaining)
            try:
                msg = self._ws.recv()
            except websocket.WebSocketTimeoutException:
                return ""
            except websocket.WebSocketConnectionClosedException as _wce:
                self._closed = True
                # Try to capture the close code and reason from the exception
                _close_status = getattr(_wce, 'status_code', None) or getattr(self._ws, 'status', None)
                _close_msg = str(_wce) if str(_wce) else getattr(self._ws, 'close_msg', b'')
                if hasattr(_close_msg, 'decode'):
                    _close_msg = _close_msg.decode('utf-8', errors='replace')
                if _close_status:
                    print(f"         🔒 WebSocket closed by server (code={_close_status}, reason={_close_msg!r})")
                    self._close_code = int(_close_status) if str(_close_status).isdigit() else self._close_code
                else:
                    print(f"         🔒 WebSocket closed by server (reason={_close_msg!r})")
                return ""
            except Exception as e:
                self._closed = True
                print(f"         ⚠️  WebSocket error during recv: {e}")
                return ""

            if msg is None or msg == "":
                self._closed = True
                print(f"         🔒 WebSocket connection ended")
                return ""

            # Log the received frame
            try:
                parsed = json.loads(msg)
                pretty = json.dumps(parsed, indent=2)
                # Capture close code from JSON-RPC error responses
                if isinstance(parsed, dict) and "error" in parsed:
                    code = parsed["error"].get("code")
                    if code in (4001, 4003, 4401):
                        self._close_code = code
            except Exception:
                pretty = msg
            indented = "\n".join("         " + ln for ln in pretty.splitlines())
            print(f"         📩 WebSocket frame received:\n{indented}")

            if wait_for is None or wait_for in msg:
                return msg
            # Got a frame but not the one we want — keep reading

        return ""

    def is_auth_error(self) -> bool:
        return self._close_code in (4001, 4003, 4401)

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass
        self._closed = True


# Auth-error signals in exception messages
_AUTH_SIGNALS = ("unauthorized", "forbidden", "token", "auth", "401", "403")

# Auth-error signals in response TEXT (OVRC returns these inside the JSON body rather than
# as a WebSocket close frame — mirrors bdd's execute_webservice check)
_TEXT_AUTH_SIGNALS = ("401", "403", "Unauthorized", "Session Timeout")


def _is_auth_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(sig in msg for sig in _AUTH_SIGNALS)


def _is_stale_connection_error(exc: Exception) -> bool:
    """Return True when the exception indicates the underlying socket silently dropped."""
    msg = str(exc).lower()
    stale_signals = (
        "socket is already closed",
        "connection is already closed",
        "eof occurred",
        "broken pipe",
        "connection reset",
        "connection aborted",
        "forcibly closed",
        "transport endpoint is not connected",
    )
    if any(sig in msg for sig in stale_signals):
        return True
    try:
        import websocket as _ws_mod
        if isinstance(exc, _ws_mod.WebSocketConnectionClosedException):
            return True
    except ImportError:
        pass
    import ssl as _ssl_mod
    if isinstance(exc, (_ssl_mod.SSLEOFError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
        return True
    return False


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

    def _make_conn(self, url: str, params: Dict[str, Any], variables: Optional[Dict[str, Any]] = None) -> "_WSConn":
        timeout = float(params.get("timeout", 10.0))
        headers = dict(params.get("headers") or {})
        # verify_ssl: check params first, then test variables (ovrc_verify_ssl / ws_verify_ssl),
        # then fall back to True.  Matches bdd's sslopt variable lookup.
        _vars = variables or {}
        verify_ssl = params.get("verify_ssl")
        if verify_ssl is None:
            verify_ssl = _vars.get("ovrc_verify_ssl", _vars.get("ws_verify_ssl", _vars.get("verify_ssl", True)))
        verify_ssl = bool(verify_ssl)

        # Inject cached token if no Authorization header set yet
        auth_url = params.get("auth_url", "")
        if auth_url and "Authorization" not in headers and auth_url in self._token_cache:
            headers["Authorization"] = f"Bearer {self._token_cache[auth_url]}"

        raw_protos = params.get("subprotocols") or params.get("protocol") or []
        if isinstance(raw_protos, str):
            raw_protos = [p.strip() for p in raw_protos.split(",") if p.strip()]

        # Determine the session identifier (used as the second subprotocol and message-ID prefix).
        # OvrC firmware servers require the auth token as the second subprotocol, not a random UUID.
        if len(raw_protos) >= 2:
            # Caller already supplied a second protocol (UUID or auth token) — use it as-is.
            session_uuid = raw_protos[1]
        elif len(raw_protos) == 1:
            # Only one named protocol; append a session identifier.
            # Priority: explicit session_token param > Bearer token from Authorization header > new UUID.
            session_token = params.get("session_token", "")
            if not session_token:
                auth_hdr = headers.get("Authorization", "")
                if auth_hdr.startswith("Bearer "):
                    session_token = auth_hdr[7:]
            if not session_token:
                session_token = str(uuid.uuid4())
            raw_protos = list(raw_protos) + [session_token]
            session_uuid = session_token
        else:
            session_uuid = str(uuid.uuid4())

        conn = _WSConn(url, headers, timeout, raw_protos or None, verify_ssl)
        conn._session_uuid = session_uuid
        # Preserve params so a later implicit reconnect reuses the SAME sessionId/subprotocols.
        # Overwrite 'subprotocols' with the fully-expanded list (including the session UUID) so
        # that a reconnect via _creation_params hits the `len >= 2` branch and keeps the same UUID
        # rather than generating a fresh one — the OvrC server tracks device sessions by sessionId.
        params_with_session = dict(params)
        params_with_session["subprotocols"] = list(raw_protos) if raw_protos else []
        conn._creation_params = params_with_session
        return conn

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _connect(self, params: Dict[str, Any], variables: Dict[str, Any]) -> bool:
        url = params.get("url", "")
        if not url:
            raise ValueError("websocket.connect requires 'url'")
        key = _pool_key(url)
        # Evict if the pooled connection is already closed
        if self._pool.has(key):
            existing = self._pool.acquire(key, lambda: None)
            if getattr(existing, "_closed", False):
                self._pool.evict(key)
            else:
                return True
        reauth = self._reauth_params(params)
        try:
            self._pool.acquire(key, lambda: self._make_conn(url, params, variables))
        except Exception as exc:
            if reauth and _is_auth_error(exc):
                self._do_reauth(reauth, params, variables)
                self._pool.evict(key)
                self._pool.acquire(key, lambda: self._make_conn(url, params, variables))
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

        # Normalize URL: when method is set (JSON-RPC mode) the method name is sent in
        # the payload, not the URL path.  Strip any trailing "/{method}" so that
        # `url: ${url}/dxUpdateFirmware, method: dxUpdateFirmware` connects to the
        # correct base WebSocket endpoint (e.g. wss://firmware.testing.ovrc.com:10444).
        if method:
            suffix = f"/{method}"
            if url.endswith(suffix):
                url = url[: -len(suffix)]
                print(f"         ℹ️  Stripped method path from URL → {url}")

        reauth = self._reauth_params(params)

        def _build_payload(conn: "_WSConn"):
            if method:
                # Use server-expected id format: {session_uuid}|{session_uuid}|{counter}
                conn._msg_counter += 1
                msg_id = f"{conn._session_uuid}|{conn._session_uuid}|{conn._msg_counter}"
                # Accept dict directly, or parse a JSON string into a dict for params
                if isinstance(data, dict):
                    params_val = data
                elif isinstance(data, str) and data.strip():
                    try:
                        params_val = json.loads(data)
                    except (json.JSONDecodeError, ValueError):
                        params_val = {}
                else:
                    params_val = {}
                # Fallback: when data is empty/None (e.g. "data:" bare key in TestRail
                # Preconditions where sub-keys end up as top-level step params after
                # _fix_step_list_indent), collect any unrecognised step params as the
                # JSON-RPC params dict.  This lets users write flat params in TestRail
                # without a nested data: block.
                if not params_val:
                    extra = {k: v for k, v in params.items()
                             if k not in _WEBSOCKET_CONTROL_PARAMS}
                    if extra:
                        params_val = extra
                # Field order matches bdd's execute_webservice: jsonrpc → id → method → params
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "method": method,
                    "params": params_val,
                }
            return data

        def _attempt(conn: "_WSConn") -> str:
            payload = _build_payload(conn)
            payload_str = json.dumps(payload, indent=2) if isinstance(payload, (dict, list)) else str(payload)
            indented = "\n".join("         " + ln for ln in payload_str.splitlines())
            print(f"         📨 Sending payload:\n{indented}")
            conn.send(payload)
            response = conn.receive(timeout=timeout, wait_for=wait_for)
            # Treat empty response on a connection that was auth-closed as an error
            if response == "" and conn.is_auth_error():
                raise ConnectionError("WebSocket closed with auth error")
            # Check for text-based auth errors in response body (OVRC returns these as JSON
            # text rather than WebSocket close frames — mirrors bdd's execute_webservice check)
            if response and any(sig in response for sig in _TEXT_AUTH_SIGNALS):
                raise ConnectionError(f"Auth error in WebSocket response: {response[:200]}")
            if not response:
                print(f"         ⚠️  No response received (timeout={timeout}s)")
            return response if response is not None else ""

        key = _pool_key(url)
        # Evict stale closed connections so we reconnect fresh.
        # If the prior connection for this URL was closed by the server (e.g. after dxGetAbout
        # responded), carry its session UUID forward so the server recognises the same session
        # when we reconnect for the next command (e.g. dxUpdateFirmware).
        reconnect_params = params
        if self._pool.has(key):
            existing = self._pool.acquire(key, lambda: None)
            _is_closed = getattr(existing, "_closed", False)
            _prior_uuid = getattr(existing, "_session_uuid", None)
            _status = "closed" if _is_closed else "open"
            print(f"         🔍 Pool: existing connection found — {_status}, session={_prior_uuid}")
            if _is_closed:
                prior_uuid = getattr(existing, "_session_uuid", None)
                if prior_uuid:
                    # Inject prior session UUID as the second subprotocol so the OvrC server
                    # recognises this reconnect as part of the same logical session.
                    reconnect_params = dict(params)
                    protos = reconnect_params.get("subprotocols") or reconnect_params.get("protocol") or []
                    if isinstance(protos, str):
                        protos = [p.strip() for p in protos.split(",") if p.strip()]
                    protos = list(protos)
                    if len(protos) >= 2:
                        protos[1] = prior_uuid          # replace whatever is there
                    elif len(protos) == 1:
                        protos.append(prior_uuid)       # add to named protocol
                    else:
                        protos = [prior_uuid]
                    reconnect_params["subprotocols"] = protos
                    reconnect_params["session_token"] = prior_uuid  # skip UUID generation
                self._pool.evict(key)
        conn: _WSConn = self._pool.acquire(
            key, lambda: self._make_conn(url, reconnect_params, variables)
        )

        try:
            result = _attempt(conn)
            # Evict if the server closed the connection during this send
            if getattr(conn, "_closed", False):
                self._pool.evict(key)
            return result
        except Exception as exc:
            self._pool.evict(key)
            if reauth and (_is_auth_error(exc) or conn.is_auth_error()):
                self._do_reauth(reauth, params, variables)
                new_conn = self._pool.acquire(key, lambda: self._make_conn(url, params, variables))
                return _attempt(new_conn)
            if _is_stale_connection_error(exc):
                print(f"         🔄 Stale connection detected — reconnecting to {url}")
                new_conn = self._pool.acquire(
                    key, lambda: self._make_conn(url, reconnect_params, variables)
                )
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
            key, lambda: self._make_conn(url, params, variables)
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
                new_conn = self._pool.acquire(key, lambda: self._make_conn(url, params, variables))
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
