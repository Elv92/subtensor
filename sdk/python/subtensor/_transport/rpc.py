"""JSON-RPC websocket session: correlation, subscriptions, reconnection.

This module knows nothing about SCALE, metadata, or Substrate semantics beyond
two things: JSON-RPC 2.0 framing (including batches and subscription
notifications), and the node's "state already discarded" error shape, which is
classified here so callers can retry against an archive node.

Design:

- One websocket per session. A single supervisor task owns the connection and
  the receive loop; requests are sent directly (under a lock) by the caller's
  task and awaited on a per-request future — there is no polling loop.
- Every pending request keeps its outgoing frame. When the connection drops,
  the supervisor reconnects and resubmits every pending frame; the caller's
  future simply resolves later. Callers never see a reconnect for plain
  requests.
- Subscriptions cannot be resumed across a reconnect (the server-side id dies
  with the connection), so each open subscription gets the failure pushed into
  its queue instead.
- Endpoint pool: the primary URL first, rotating through ``fallback_urls`` when
  an endpoint fails to connect or exhausts ``max_retries`` response timeouts.
  With ``retry_forever`` the pool is cycled indefinitely, with a growing pause
  between full cycles.
- The websocket connection itself is injectable (``connect_factory``) so tests
  drive the session against an in-process fake server.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, Protocol, Union

from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

from .errors import MaxRetriesExceeded, StateDiscardedError, SubstrateRequestException
from .utils import json

logger = logging.getLogger("subtensor.transport")
raw_logger = logging.getLogger("subtensor.transport.raw_websocket")

_STATE_DISCARDED_NEEDLE = "State already discarded for "


class WsConnection(Protocol):
    """The slice of a websocket connection the session uses (injectable)."""

    async def send(self, message: str) -> None: ...

    async def recv(self) -> Union[str, bytes]: ...

    async def close(self) -> None: ...


ConnectFactory = Callable[[str], Awaitable[WsConnection]]


async def _default_connect(url: str) -> WsConnection:
    return await asyncio.wait_for(
        ws_connect(url, max_size=2**32, write_limit=2**16), timeout=10.0
    )


def classify_rpc_error(error: dict) -> SubstrateRequestException:
    """Build the exception for a JSON-RPC error payload."""
    message = str(error.get("message", ""))
    data = error.get("data")
    if isinstance(data, str) and _STATE_DISCARDED_NEEDLE in data:
        return StateDiscardedError(data.split(_STATE_DISCARDED_NEEDLE)[1].strip())
    if _STATE_DISCARDED_NEEDLE in message:
        return StateDiscardedError(message.split(_STATE_DISCARDED_NEEDLE)[1].strip())
    return SubstrateRequestException({"error": error})


class Subscription:
    """An active server-push subscription, consumed with ``async for``."""

    def __init__(self, session: "RpcSession", subscription_id: str, unsubscribe_method: str):
        self.subscription_id = subscription_id
        self._session = session
        self._unsubscribe_method = unsubscribe_method
        self._queue: asyncio.Queue = asyncio.Queue()
        self._closed = False

    def __aiter__(self) -> AsyncIterator[Any]:
        return self

    async def __anext__(self) -> Any:
        if self._closed:
            raise StopAsyncIteration
        item = await self._queue.get()
        if isinstance(item, Exception):
            self._closed = True
            raise item
        if item is _SUBSCRIPTION_END:
            self._closed = True
            raise StopAsyncIteration
        return item

    async def unsubscribe(self) -> None:
        """Tell the node to stop, and end local iteration."""
        if self._closed:
            return
        self._closed = True
        self._session._subscriptions.pop(self.subscription_id, None)
        with contextlib.suppress(Exception):
            await self._session.request(self._unsubscribe_method, [self.subscription_id])

    def _push(self, item: Any) -> None:
        self._queue.put_nowait(item)


_SUBSCRIPTION_END = object()


class _Pending:
    __slots__ = ("future", "frame")

    def __init__(self, future: asyncio.Future, frame: dict):
        self.future = future
        self.frame = frame


class RpcSession:
    def __init__(
        self,
        url: str,
        *,
        fallback_urls: Optional[list[str]] = None,
        retry_forever: bool = False,
        max_retries: int = 5,
        response_timeout: float = 60.0,
        connect_factory: Optional[ConnectFactory] = None,
    ):
        """A JSON-RPC session over one websocket.

        Args:
            url: primary ``ws://`` / ``wss://`` endpoint.
            fallback_urls: same-chain endpoints rotated to on connection failure.
            retry_forever: never give up on connection failures; keep cycling
                the endpoint pool until one answers.
            max_retries: response timeouts tolerated per endpoint before
                rotating to the next one.
            response_timeout: seconds without *any* inbound frame (while
                requests are pending) before the connection is presumed dead
                and reestablished.
            connect_factory: replaces the real websocket dial (for tests).
        """
        self._urls = [url] + [u for u in (fallback_urls or []) if u != url]
        self._url_index = 0
        self._retry_forever = retry_forever
        self._max_retries = max_retries
        self._response_timeout = response_timeout
        self._connect = connect_factory or _default_connect

        self._ws: Optional[WsConnection] = None
        self._supervisor: Optional[asyncio.Task] = None
        self._connected = asyncio.Event()
        self._closing = False
        self._ids = itertools.count(1)
        self._pending: dict[int, _Pending] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._send_lock = asyncio.Lock()
        self._timeouts_on_endpoint = 0
        self._total_timeouts = 0

    @property
    def url(self) -> str:
        """The endpoint currently in use (rotates through the pool on failure)."""
        return self._urls[self._url_index]

    # -- lifecycle -------------------------------------------------------------

    async def connect(self) -> None:
        if self._supervisor is not None and not self._supervisor.done():
            await self._connected.wait()
            return
        self._closing = False
        self._supervisor = asyncio.create_task(self._run(), name="rpc-session")
        # Surface immediate connection failures to the caller instead of
        # parking them on the first request.
        connected = asyncio.create_task(self._connected.wait())
        done, _ = await asyncio.wait(
            {connected, self._supervisor}, return_when=asyncio.FIRST_COMPLETED
        )
        if self._supervisor in done:
            connected.cancel()
            error = self._supervisor.exception()
            if error is not None:
                raise error
            raise SubstrateRequestException("connection closed during connect")

    async def close(self) -> None:
        self._closing = True
        if self._supervisor is not None:
            self._supervisor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._supervisor
            self._supervisor = None
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        self._connected.clear()
        shutdown = SubstrateRequestException("RPC session closed")
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.set_exception(shutdown)
        self._pending.clear()
        for sub in list(self._subscriptions.values()):
            sub._push(_SUBSCRIPTION_END)
        self._subscriptions.clear()

    async def __aenter__(self) -> "RpcSession":
        await self.connect()
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    # -- requests ----------------------------------------------------------------

    async def request(self, method: str, params: Optional[list] = None) -> Any:
        """One JSON-RPC request; returns the ``result`` or raises."""
        frame = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or []}
        future = await self._submit(frame)
        response = await future
        return self._unwrap(response)

    async def request_batch(self, requests: list[tuple[str, Optional[list]]]) -> list[Any]:
        """Send several requests as one JSON-RPC 2.0 batch frame.

        Responses are unwrapped in request order; the first error raises.
        """
        if not requests:
            return []
        frames = [
            {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or []}
            for method, params in requests
        ]
        futures = await self._submit_batch(frames)
        responses = await asyncio.gather(*futures)
        return [self._unwrap(response) for response in responses]

    async def subscribe(
        self, method: str, params: Optional[list], unsubscribe_method: str
    ) -> Subscription:
        """Open a subscription; iterate the returned object for updates.

        Each yielded item is the notification's ``params`` dict (with
        ``result`` and ``subscription`` keys). A connection drop while the
        subscription is open raises out of the iterator — server-side
        subscription state does not survive a reconnect.
        """
        subscription_id = await self.request(method, params)
        if not isinstance(subscription_id, (str, int)):
            raise SubstrateRequestException(
                {"error": {"message": f"unexpected subscription id: {subscription_id!r}"}}
            )
        subscription_id = str(subscription_id)
        subscription = Subscription(self, subscription_id, unsubscribe_method)
        # Updates may have raced the subscribe response into the early queue.
        early = self._subscriptions.pop(subscription_id, None)
        if isinstance(early, _EarlyUpdates):
            for item in early.items:
                subscription._push(item)
        self._subscriptions[subscription_id] = subscription
        return subscription

    # -- internals -----------------------------------------------------------------

    @staticmethod
    def _unwrap(response: dict) -> Any:
        if "error" in response:
            raise classify_rpc_error(response["error"])
        if "result" not in response:
            raise SubstrateRequestException(response)
        return response["result"]

    async def _submit(self, frame: dict) -> asyncio.Future:
        future = asyncio.get_running_loop().create_future()
        self._pending[frame["id"]] = _Pending(future, frame)
        await self._send_frame(frame)
        return future

    async def _submit_batch(self, frames: list[dict]) -> list[asyncio.Future]:
        loop = asyncio.get_running_loop()
        futures = []
        for frame in frames:
            future = loop.create_future()
            self._pending[frame["id"]] = _Pending(future, frame)
            futures.append(future)
        await self._send_frame(frames, batch_ids=[f["id"] for f in frames])
        return futures

    async def _send_frame(self, frame: Any, batch_ids: Optional[list[int]] = None) -> None:
        """Serialize and send one frame, connecting first if needed.

        A send failure is not fatal to the request: the pending entry keeps the
        frame, and the supervisor resubmits it after reconnecting.
        """
        if self._supervisor is None or self._supervisor.done():
            await self.connect()
        await self._connected.wait()
        text = json.dumps(frame)
        if raw_logger.isEnabledFor(logging.DEBUG):
            raw_logger.debug(f"WEBSOCKET_SEND> {text}")
        try:
            async with self._send_lock:
                assert self._ws is not None
                await self._ws.send(text)
        except Exception as error:  # supervisor will notice and resubmit
            logger.debug(f"send failed ({error!r}); leaving frame for resubmission")

    def _fail_all(self, error: Exception) -> None:
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.set_exception(error)
        self._pending.clear()
        self._fail_subscriptions(error)

    def _fail_subscriptions(self, error: Exception) -> None:
        if not self._subscriptions:
            return
        dropped = [s for s in self._subscriptions.values() if isinstance(s, Subscription)]
        if dropped:
            logger.warning(
                "Connection lost with %d open subscription(s); they cannot be resumed.",
                len(dropped),
            )
        for sub in dropped:
            sub._push(
                SubstrateRequestException(
                    "Connection lost while waiting for a subscription response "
                    "(e.g. extrinsic finalization). The transaction may already be "
                    "on chain — verify balances before retrying."
                )
            )
        self._subscriptions.clear()

    async def _run(self) -> None:
        """Supervisor: connect, pump frames, reconnect with resubmission."""
        while not self._closing:
            try:
                self._ws = await self._dial()
            except MaxRetriesExceeded as error:
                self._fail_all(error)
                raise
            self._connected.set()
            self._timeouts_on_endpoint = 0
            await self._resubmit_pending()
            reason = await self._pump()
            self._connected.clear()
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
            if self._closing or isinstance(reason, ConnectionClosedOK):
                return
            # Any abnormal end: subscriptions die, plain requests survive.
            self._fail_subscriptions(reason)
            if isinstance(reason, TimeoutError):
                self._timeouts_on_endpoint += 1
                self._total_timeouts += 1
                if self._timeouts_on_endpoint >= self._max_retries:
                    self._rotate_url()
                    self._timeouts_on_endpoint = 0
                if (
                    not self._retry_forever
                    and self._total_timeouts >= self._max_retries * len(self._urls)
                ):
                    error = MaxRetriesExceeded({"error": {"message": "Max retries exceeded."}})
                    self._fail_all(error)
                    return
            logger.info(f"Connection to {self.url} lost ({reason!r}); reconnecting")

    async def _dial(self) -> WsConnection:
        """Open a websocket to the first reachable endpoint in the pool."""
        cycle = 0
        last_error: Optional[Exception] = None
        while True:
            for _ in range(len(self._urls)):
                try:
                    return await self._connect(self.url)
                except Exception as error:
                    last_error = error
                    logger.info(
                        f"Could not connect to {self.url}: {type(error).__name__}: {error}"
                    )
                    self._rotate_url()
            cycle += 1
            if not self._retry_forever:
                assert last_error is not None
                if isinstance(last_error, SubstrateRequestException):
                    raise last_error
                raise MaxRetriesExceeded(
                    {"error": {"message": f"could not connect to any endpoint: {last_error}"}}
                )
            delay = min(2.0 * cycle, 30.0)
            logger.warning(f"All endpoints unreachable; retrying in {delay:.0f}s")
            await asyncio.sleep(delay)

    def _rotate_url(self) -> None:
        if len(self._urls) == 1:
            return
        self._url_index = (self._url_index + 1) % len(self._urls)
        logger.info(f"Falling back to endpoint {self.url}")

    async def _resubmit_pending(self) -> None:
        """Re-send the frame of every request still awaiting a response."""
        if not self._pending:
            return
        logger.debug(f"Resubmitting {len(self._pending)} in-flight request(s)")
        for pending in list(self._pending.values()):
            if pending.future.done():
                continue
            text = json.dumps(pending.frame)
            try:
                async with self._send_lock:
                    assert self._ws is not None
                    await self._ws.send(text)
            except Exception as error:
                logger.debug(f"resubmission failed ({error!r}); will retry on next connect")
                return

    async def _pump(self) -> Exception:
        """Receive frames until the connection ends; returns the reason."""
        assert self._ws is not None
        ws = self._ws
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=self._response_timeout)
            except asyncio.TimeoutError:
                if not self._pending and not self._subscriptions:
                    continue  # idle silence is fine; only unanswered work times out
                return TimeoutError(f"no response from {self.url} in {self._response_timeout}s")
            except ConnectionClosedOK as error:
                if self._pending or self._subscriptions:
                    # The server hung up mid-request: treat as abnormal.
                    return ConnectionClosed(error.rcvd, error.sent)
                return error
            except Exception as error:
                return error
            if isinstance(raw, bytes):
                raw = raw.decode()
            if raw_logger.isEnabledFor(logging.DEBUG):
                raw_logger.debug(f"WEBSOCKET_RECEIVE> {raw}")
            try:
                message = json.loads(raw)
            except ValueError:
                logger.warning("Dropping unparseable frame from node")
                continue
            if isinstance(message, list):
                for item in message:
                    self._dispatch(item)
            else:
                self._dispatch(message)

    def _dispatch(self, message: dict) -> None:
        if "id" in message and message["id"] is not None:
            pending = self._pending.pop(message["id"], None)
            if pending is None:
                logger.debug(f"Response for unknown id {message['id']} (late reply?); dropped")
                return
            if not pending.future.done():
                pending.future.set_result(message)
            return
        params = message.get("params")
        if isinstance(params, dict) and "subscription" in params:
            sub_id = str(params["subscription"])
            target = self._subscriptions.get(sub_id)
            if target is None:
                # Update raced ahead of the subscribe response: buffer it.
                target = _EarlyUpdates()
                self._subscriptions[sub_id] = target
            target._push(params)
            return
        logger.debug(f"Unroutable frame dropped: {str(message)[:200]}")


class _EarlyUpdates:
    """Buffer for subscription updates that arrive before ``subscribe`` returns."""

    def __init__(self):
        self.items: list = []

    def _push(self, item: Any) -> None:
        self.items.append(item)
