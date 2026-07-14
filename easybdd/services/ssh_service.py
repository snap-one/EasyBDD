"""
SSH service for Easy BDD Framework.

Paramiko-based SSH client with persistent connection pooling. Designed for
interactive device sessions (routers, switches, WattBox CLI, etc.) where
multiple commands need to run in the same shell session.

  ssh.*        — stateful multi-command sessions with connection reuse
  command.ssh  — one-shot subprocess; no prompt support, no session pool

YAML actions:
  ssh.connect    — open an SSH connection (also auto-opened on first command)
  ssh.command    — run a command and capture output
  ssh.disconnect — close the connection

Shorthand (connect + command in one step):

  - ssh.command:
      host: 192.168.1.1
      username: admin
      password: admin123
      command: show version
      store_as: fw_version

Interactive shell (prompt-based, e.g. WattBox, Araknis, Cisco):

  - ssh.command:
      host: ${ip_address}
      username: wattbox
      password: SnapAV704
      prompt: '>'           # wait for this substring before returning
      command: '?Model'     # quote commands starting with ? ! * & |
      store_as: model

  - ssh.command:
      host: ${ip_address}
      username: araknis
      password: SnapAV704!
      prompt: '#'           # matches 'AN-210-SW-16-POE#' — substring check
      command: show version

Stateful multi-command session:

  - ssh.connect:
      host: 192.168.1.1
      username: admin
      password: admin123

  - ssh.command:
      host: 192.168.1.1
      command: show version
      store_as: version_output

  - ssh.command:
      host: 192.168.1.1
      command: show interfaces
      prompt: '#'
      store_as: interfaces

  - ssh.disconnect:
      host: 192.168.1.1

Key auth:

  - ssh.connect:
      host: 192.168.1.1
      username: admin
      key_filename: /home/jenkins/.ssh/id_rsa
      passphrase: ''          # omit if key has no passphrase

YAML quoting rules:
  - Always quote prompt: values that contain '#' (e.g. prompt: 'AN-210-SW-16-POE#')
    An unquoted '#' preceded by whitespace is treated as a YAML comment → null.
  - Quote command: values that start with ?, !, *, &, or | (e.g. command: '?Model').
  - An empty 'command:' or 'prompt:' key is parsed as null, not an empty string.
  The parser warns about null parameters before the run starts.
"""

import socket
import time
from typing import Any, Dict, Optional

from ..core.connection_pool import ConnectionPool

_DEFAULT_PORT = 22
_DEFAULT_TIMEOUT = 10.0
_DEFAULT_PROMPT = "#"
_SHELL_TIMEOUT = 30.0


def _pool_key(host: str, port: int) -> str:
    return f"ssh://{host}:{port}"


class _SSHConn:
    """Paramiko SSH connection with optional interactive shell channel."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str = "",
        key_filename: str = "",
        passphrase: str = "",
        timeout: float = _DEFAULT_TIMEOUT,
        look_for_keys: bool = True,
        allow_agent: bool = True,
    ):
        try:
            import paramiko
        except ImportError:
            raise RuntimeError("paramiko is not installed. Run: pip install paramiko")

        print(f"         🔌 SSH connecting to {host}:{port} as {username!r}...")
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: Dict[str, Any] = dict(
            hostname=host,
            port=port,
            username=username,
            timeout=timeout,
            look_for_keys=look_for_keys,
            allow_agent=allow_agent,
        )
        if key_filename:
            connect_kwargs["key_filename"] = key_filename
            if passphrase:
                connect_kwargs["passphrase"] = passphrase
        elif password:
            connect_kwargs["password"] = password

        self._client.connect(**connect_kwargs)
        self._shell: Optional[Any] = None  # lazy-opened interactive shell
        self._host = host
        self._port = port
        print(f"         ✅ SSH connected to {host}:{port}")

    # ------------------------------------------------------------------ #
    # exec_command mode (one-shot, clean, no prompt needed)               #
    # ------------------------------------------------------------------ #

    def exec_command(self, command: str, timeout: float = _SHELL_TIMEOUT) -> str:
        """Run a single command via exec_command. Best for non-interactive commands."""
        print(f"         📤 SSH exec: {command!r}")
        stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        stdout.channel.set_combine_stderr(True)
        out = stdout.read().decode("utf-8", errors="replace")
        print(f"         📥 SSH output ({len(out)} chars)")
        return out

    # ------------------------------------------------------------------ #
    # Interactive shell mode (prompt-based, persistent session)           #
    # ------------------------------------------------------------------ #

    def _open_shell(self, timeout: float = _DEFAULT_TIMEOUT) -> Any:
        if self._shell is None:
            print(f"         🖥️  Opening interactive shell...")
            self._shell = self._client.invoke_shell(width=220, height=50)
            self._shell.settimeout(timeout)
            # Drain initial banner
            time.sleep(0.3)
            self._drain(timeout=2.0)
        return self._shell

    def _drain(self, timeout: float = 1.0) -> str:
        """Read and discard buffered output."""
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._shell.settimeout(min(deadline - time.time(), 0.2))
            try:
                chunk = self._shell.recv(4096)
                if not chunk:
                    break
                buf += chunk
            except socket.timeout:
                break
            except Exception:
                break
        return buf.decode("utf-8", errors="replace")

    def shell_command(self, command: str, prompt: str, timeout: float = _SHELL_TIMEOUT) -> str:
        """Send a command on the interactive shell and read until prompt."""
        sh = self._open_shell(timeout)
        print(f"         📤 SSH shell: {command!r} (waiting for {prompt!r})")
        sh.sendall((command + "\n").encode("utf-8"))

        prompt_bytes = prompt.encode("utf-8")
        buf = b""
        deadline = time.time() + timeout
        last_recv = time.time()
        idle_timeout = 5.0
        while time.time() < deadline:
            sh.settimeout(min(deadline - time.time(), 0.5))
            try:
                chunk = sh.recv(4096)
                if not chunk:
                    # recv returning empty bytes means the server closed the
                    # connection (EOF). Raise so _command can reconnect.
                    raise ConnectionError("SSH shell: connection closed by remote host (0 bytes received)")
                buf += chunk
                last_recv = time.time()
                if prompt_bytes in buf:
                    break
            except socket.timeout:
                # Keep reading until the prompt arrives OR 5s of silence
                if (time.time() - last_recv) >= idle_timeout:
                    break
                continue
            except ConnectionError:
                raise
            except Exception:
                break

        result = buf.decode("utf-8", errors="replace")
        print(f"         📥 SSH output ({len(result)} chars)")
        return result

    def close(self) -> None:
        try:
            if self._shell:
                self._shell.close()
        except Exception:
            pass
        try:
            self._client.close()
        except Exception:
            pass


class SSHService:
    """Stateful SSH service backed by a shared ConnectionPool."""

    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    # ------------------------------------------------------------------ #
    # Action dispatch                                                      #
    # ------------------------------------------------------------------ #

    def execute(self, action: str, params: Dict[str, Any], variables: Dict[str, Any]) -> Any:
        action_lower = action.lower()

        if "connect" in action_lower:
            return self._connect(params)
        if "command" in action_lower or "send" in action_lower or "run" in action_lower:
            return self._command(params)
        if "disconnect" in action_lower or "close" in action_lower:
            return self._disconnect(params)

        raise ValueError(
            f"Unknown ssh action: {action!r}. Use: ssh.connect, ssh.command, ssh.disconnect"
        )

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _connect(self, params: Dict[str, Any]) -> bool:
        host = params.get("host", "")
        port = int(params.get("port", _DEFAULT_PORT))
        if not host:
            raise ValueError("ssh.connect requires 'host'")
        key = _pool_key(host, port)
        if self._pool.has(key):
            print(f"         ♻️  Reusing existing SSH connection to {host}:{port}")
            return True
        self._pool.acquire(key, lambda: self._make_conn(params, host, port))
        return True

    def _command(self, params: Dict[str, Any]) -> str:
        host = params.get("host") or ""
        port = int(params.get("port") or _DEFAULT_PORT)
        command = params.get("command") or ""
        timeout = float(params.get("timeout") or _SHELL_TIMEOUT)
        prompt = params.get("prompt") or ""  # if set, use interactive shell mode
        use_shell = bool(params.get("use_shell", False)) or bool(prompt)

        if not host:
            raise ValueError(
                "ssh.command requires 'host' — got null/empty. "
                "Check your YAML for a missing or null 'host:' value."
            )
        if not command:
            raise ValueError(
                f"ssh.command requires 'command' — got {params.get('command')!r}. "
                "Check your YAML: unquoted '#' starts a comment (use quotes), "
                "and an empty 'command:' line becomes null."
            )

        key = _pool_key(host, port)

        for attempt in range(2):
            conn: _SSHConn = self._pool.acquire(key, lambda: self._make_conn(params, host, port))
            try:
                if use_shell:
                    result = conn.shell_command(command, prompt or _DEFAULT_PROMPT, timeout)
                else:
                    result = conn.exec_command(command, timeout)
                return result
            except Exception as exc:
                self._pool.evict(key)
                if attempt == 0:
                    print(f"           ⚠️  SSH connection lost ({exc!s}) — reconnecting to {host}:{port}...")
                    continue
                raise
        raise RuntimeError("SSH: reconnect loop exhausted")

    def _disconnect(self, params: Dict[str, Any]) -> bool:
        host = params.get("host", "")
        port = int(params.get("port", _DEFAULT_PORT))
        if not host:
            raise ValueError("ssh.disconnect requires 'host'")
        key = _pool_key(host, port)
        print(f"         🔌 SSH disconnecting from {host}:{port}")
        self._pool.evict(key)
        return True

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _make_conn(self, params: Dict[str, Any], host: str, port: int) -> _SSHConn:
        return _SSHConn(
            host=host,
            port=port,
            username=params.get("username", ""),
            password=params.get("password", ""),
            key_filename=params.get("key_filename", ""),
            passphrase=params.get("passphrase", ""),
            timeout=float(params.get("timeout", _DEFAULT_TIMEOUT)),
            look_for_keys=bool(params.get("look_for_keys", True)),
            allow_agent=bool(params.get("allow_agent", True)),
        )
