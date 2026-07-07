"""Ensure the extension bridge is running and ready before signing."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from .bridge import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT
from .browser import open_bridge_page
from .client import BridgeClient, BridgeError

DEFAULT_BRIDGE_PID_PATH = Path.home() / ".bittensor" / "extension_bridge.pid"


def bridge_pid_path() -> Path:
    return Path(os.getenv("SUBTENSOR_EXTENSION_BRIDGE_PID") or DEFAULT_BRIDGE_PID_PATH)


def bridge_http_url(host: str = DEFAULT_BRIDGE_HOST, port: int = DEFAULT_BRIDGE_PORT) -> str:
    return f"http://{host}:{port}/"


def bridge_ws_url(
    host: str = DEFAULT_BRIDGE_HOST,
    port: int = DEFAULT_BRIDGE_PORT,
    *,
    bridge_url: Optional[str] = None,
) -> str:
    if bridge_url:
        parsed = urlparse(bridge_url)
        if parsed.scheme in ("ws", "wss"):
            return bridge_url
        if parsed.scheme in ("http", "https"):
            host = parsed.hostname or host
            port = parsed.port or port
    return f"ws://{host}:{port}/ws"


def _parse_bridge_target(bridge_url: Optional[str]) -> tuple[str, int]:
    if not bridge_url:
        return DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT
    parsed = urlparse(bridge_url)
    host = parsed.hostname or DEFAULT_BRIDGE_HOST
    port = parsed.port or DEFAULT_BRIDGE_PORT
    return host, port


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_daemon_pid() -> Optional[int]:
    path = bridge_pid_path()
    if not path.is_file():
        return None
    try:
        pid = int(path.read_text().strip())
    except ValueError:
        return None
    if not _process_alive(pid):
        path.unlink(missing_ok=True)
        return None
    return pid


def start_bridge_daemon(
    *,
    host: str = DEFAULT_BRIDGE_HOST,
    port: int = DEFAULT_BRIDGE_PORT,
) -> None:
    """Spawn a detached bridge process if one is not already running."""
    if _read_daemon_pid() is not None:
        return

    pid_path = bridge_pid_path()
    pid_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "subtensor.extension.daemon",
        "--host",
        host,
        "--port",
        str(port),
        "--pid-file",
        str(pid_path),
    ]
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


async def bridge_status(url: str) -> dict:
    async with BridgeClient(url) as client:
        result = await client.request("bridge.status")
        return result if isinstance(result, dict) else {}


async def bridge_is_reachable(url: str) -> bool:
    try:
        await bridge_status(url)
        return True
    except Exception:
        return False


async def wait_for_bridge(url: str, *, timeout: float = 15.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await bridge_is_reachable(url):
            return
        await asyncio.sleep(0.15)
    raise BridgeError("extension bridge did not start; try again in a moment")


async def wait_for_extension(
    url: str,
    *,
    timeout: float = 180.0,
    open_browser: bool = True,
    host: str = DEFAULT_BRIDGE_HOST,
    port: int = DEFAULT_BRIDGE_PORT,
    browser: Optional[str] = None,
    on_waiting: Optional[Callable[[str, dict], None]] = None,
) -> None:
    """Wait until a browser tab is connected and an extension is authorized."""
    http_url = bridge_http_url(host, port)
    opened = False
    deadline = asyncio.get_running_loop().time() + timeout
    last_notice = 0.0

    while asyncio.get_running_loop().time() < deadline:
        try:
            status = await bridge_status(url)
        except Exception:
            status = {}

        account_count = status.get("account_count")
        if status.get("browser_connected") and isinstance(account_count, int) and account_count > 0:
            return

        now = asyncio.get_running_loop().time()
        if on_waiting is not None and now - last_notice >= 5.0:
            on_waiting(http_url, status)
            last_notice = now

        if open_browser and not opened:
            open_bridge_page(http_url, browser=browser)
            opened = True
        await asyncio.sleep(0.25)

    raise BridgeError(
        "extension not ready — in the browser tab, allow “Subtensor SDK” to access your "
        f"extension, then run the command again: {http_url}"
    )


async def ensure_bridge(
    *,
    bridge_url: Optional[str] = None,
    host: str = DEFAULT_BRIDGE_HOST,
    port: int = DEFAULT_BRIDGE_PORT,
    open_browser: bool = True,
    browser: Optional[str] = None,
    on_waiting: Optional[Callable[[str, dict], None]] = None,
) -> str:
    """Return a bridge WebSocket URL, starting the daemon and browser flow if needed."""
    host, port = _parse_bridge_target(bridge_url)
    url = bridge_ws_url(host, port)

    if not await bridge_is_reachable(url):
        start_bridge_daemon(host=host, port=port)
        await wait_for_bridge(url)

    status = await bridge_status(url)
    account_count = status.get("account_count")
    browser_connected = bool(status.get("browser_connected"))

    if not browser_connected or not (isinstance(account_count, int) and account_count > 0):
        await wait_for_extension(
            url,
            open_browser=open_browser,
            host=host,
            port=port,
            browser=browser,
            on_waiting=on_waiting,
        )

    return url


async def stop_bridge_daemon() -> bool:
    pid = _read_daemon_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        bridge_pid_path().unlink(missing_ok=True)
        return False
    bridge_pid_path().unlink(missing_ok=True)
    return True
