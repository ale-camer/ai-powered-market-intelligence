"""WebSocket streaming module for real-time market anomaly alerts."""

import asyncio
import inspect
import json
from collections.abc import Mapping
from datetime import UTC, datetime

from market_intel.core.logger import get_logger
from market_intel.core.metrics import set_websocket_connections
from market_intel.core.schemas import AlertItem
from market_intel.core.security import verify_access_token

logger = get_logger("market_intel.api.websocket")


class WebSocketDisconnect(Exception):
    """Raised when a WebSocket connection is closed."""

    def __init__(self, code: int = 1000, reason: str | None = None) -> None:
        """Initialize disconnect exception with close code and optional reason."""
        super().__init__(f"WebSocket disconnected with code {code}")
        self.code = code
        self.reason = reason


class ASGIWebSocketAdapter:
    """Lightweight adapter wrapping ASGI scope, receive, and send callables."""

    def __init__(
        self,
        scope: dict[str, object],
        receive: object,
        send: object,
    ) -> None:
        """Initialize ASGI WebSocket adapter.

        Args:
            scope: ASGI scope dictionary.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        self.scope = scope
        self._receive = receive
        self._send = send
        self.client_state = "connecting"

    async def _send_frame(self, frame: Mapping[str, object]) -> None:
        """Safely send an ASGI message frame."""
        if callable(self._send):
            res = self._send(dict(frame))
            if inspect.isawaitable(res):
                await res

    async def accept(self) -> None:
        """Accept the WebSocket connection."""
        self.client_state = "connected"
        await self._send_frame({"type": "websocket.accept"})

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the WebSocket connection with a given code and reason."""
        self.client_state = "disconnected"
        await self._send_frame(
            {
                "type": "websocket.close",
                "code": code,
                "reason": reason,
            }
        )

    async def send_text(self, data: str) -> None:
        """Send a text frame over the WebSocket."""
        await self._send_frame(
            {
                "type": "websocket.send",
                "text": data,
            }
        )

    async def send_json(self, data: Mapping[str, object]) -> None:
        """Send a JSON payload over the WebSocket."""
        await self.send_text(json.dumps(dict(data)))

    async def receive_text(self) -> str:
        """Receive a text frame from the WebSocket."""
        if callable(self._receive):
            res = self._receive()
            msg = await res if inspect.isawaitable(res) else res
            if not isinstance(msg, dict):
                return ""
            msg_type = msg.get("type")
            if msg_type == "websocket.disconnect":
                code = int(msg.get("code", 1000))
                raise WebSocketDisconnect(code=code)
            raw_text = msg.get("text", "")
            return str(raw_text) if raw_text is not None else ""
        return ""

    async def receive_json(self) -> dict[str, object]:
        """Receive a JSON payload from the WebSocket."""
        text = await self.receive_text()
        parsed: object = json.loads(text) if text else {}
        return parsed if isinstance(parsed, dict) else {}


class ConnectionManager:
    """Manages active WebSocket connections, broadcasting, and heartbeat keepalive."""

    def __init__(self) -> None:
        """Initialize ConnectionManager with an empty set of active connections."""
        self.active_connections: list[object] = []
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def connect(self, websocket: object) -> None:
        """Accept connection and register client.

        Args:
            websocket: Connected WebSocket instance or adapter.
        """
        accept_fn = getattr(websocket, "accept", None)
        if callable(accept_fn):
            await accept_fn()

        if websocket not in self.active_connections:
            self.active_connections.append(websocket)
            logger.info(
                f"WebSocket client connected. Active connections: {len(self.active_connections)}"
            )
            set_websocket_connections(len(self.active_connections))

    def disconnect(self, websocket: object) -> None:
        """Unregister client connection.

        Args:
            websocket: WebSocket instance or adapter to unregister.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                f"WebSocket client disconnected. Active connections: {len(self.active_connections)}"
            )
            set_websocket_connections(len(self.active_connections))

    async def send_personal_message(
        self,
        message: Mapping[str, object] | str,
        websocket: object,
    ) -> None:
        """Send message directly to a specific connected client.

        Args:
            message: Mapping or string to send.
            websocket: Target client connection.
        """
        payload_str = json.dumps(dict(message)) if isinstance(message, Mapping) else str(message)
        send_fn = getattr(websocket, "send_text", None)
        if callable(send_fn):
            await send_fn(payload_str)

    async def broadcast(self, message: Mapping[str, object] | str) -> None:
        """Broadcast message to all active clients concurrently, pruning dead connections.

        Args:
            message: Mapping or string message to broadcast.
        """
        if not self.active_connections:
            return

        payload_str = json.dumps(dict(message)) if isinstance(message, Mapping) else str(message)
        dead_connections: list[object] = []

        async def _safe_send(ws: object) -> None:
            try:
                send_fn = getattr(ws, "send_text", None)
                if callable(send_fn):
                    await send_fn(payload_str)
            except Exception as exc:
                logger.debug(f"Failed to send to client ({exc}); scheduling disconnect.")
                dead_connections.append(ws)

        await asyncio.gather(*(_safe_send(ws) for ws in list(self.active_connections)))

        for dead_ws in dead_connections:
            self.disconnect(dead_ws)

    async def broadcast_alert(self, alert: AlertItem | dict[str, object]) -> None:
        """Broadcast an anomaly alert event to all connected clients.

        Args:
            alert: AlertItem model instance or raw dictionary.
        """
        if isinstance(alert, AlertItem):
            alert_data: dict[str, object] = alert.model_dump(mode="json")
        else:
            alert_data = alert

        event_payload = {
            "event": "alert",
            "data": alert_data,
        }
        await self.broadcast(event_payload)

    def create_heartbeat_payload(self) -> dict[str, object]:
        """Construct standard heartbeat ping payload.

        Returns:
            Dictionary containing ping event and current UTC timestamp.
        """
        return {
            "type": "ping",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def broadcast_heartbeat(self) -> None:
        """Broadcast periodic ping heartbeat to all active connections."""
        payload = self.create_heartbeat_payload()
        await self.broadcast(payload)

    def start_heartbeat_loop(self, interval_seconds: float = 30.0) -> asyncio.Task[None]:
        """Start background heartbeat loop broadcasting ping every interval_seconds.

        Args:
            interval_seconds: Interval in seconds between pings (default: 30.0).

        Returns:
            Created asyncio.Task.
        """

        async def _loop() -> None:
            while True:
                await asyncio.sleep(interval_seconds)
                try:
                    await self.broadcast_heartbeat()
                except Exception as exc:
                    logger.debug(f"Error during heartbeat broadcast: {exc}")

        self._heartbeat_task = asyncio.create_task(_loop())
        return self._heartbeat_task

    def stop_heartbeat_loop(self) -> None:
        """Stop background heartbeat loop if currently active."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None


connection_manager = ConnectionManager()


async def handle_websocket_alerts(
    websocket: object,
    token: str | None,
    manager: ConnectionManager | None = None,
    secret_key: str | None = None,
) -> None:
    """Authenticate and manage a WebSocket connection for /ws/alerts.

    Args:
        websocket: Client WebSocket instance or ASGI adapter.
        token: Query parameter JWT token.
        manager: Optional ConnectionManager (defaults to connection_manager singleton).
        secret_key: Optional HMAC secret key override.
    """
    mgr = manager or connection_manager

    # 1. Authenticate JWT token
    claims = verify_access_token(token or "", secret_key=secret_key)
    if claims is None:
        logger.warning("Rejected WebSocket connection: missing or invalid JWT token.")
        close_fn = getattr(websocket, "close", None)
        if callable(close_fn):
            await close_fn(code=1008, reason="Unauthorized: invalid or missing token")
        return

    # 2. Register connection
    await mgr.connect(websocket)

    # 3. Connection listen loop
    try:
        while True:
            receive_fn = getattr(websocket, "receive_text", None)
            if not callable(receive_fn):
                break
            raw_msg = await receive_fn()
            if not raw_msg:
                continue

            try:
                parsed_msg = json.loads(raw_msg)
                if isinstance(parsed_msg, dict) and parsed_msg.get("type") == "pong":
                    logger.debug("Received pong keepalive from client.")
            except (json.JSONDecodeError, ValueError):
                pass
    except (WebSocketDisconnect, ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        mgr.disconnect(websocket)
