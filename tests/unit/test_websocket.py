"""Unit tests for WebSocket alert streaming, ConnectionManager, and JWT auth (Issue #16)."""

import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime

import pytest

from market_intel.api.app import MarketIntelASGIApp, create_app
from market_intel.api.websocket import (
    ASGIWebSocketAdapter,
    ConnectionManager,
    WebSocketDisconnect,
    handle_websocket_alerts,
)
from market_intel.core.schemas import AlertItem
from market_intel.core.security import create_access_token, verify_access_token


class MockWebSocket:
    """Mock WebSocket client for unit testing connection manager and endpoints."""

    def __init__(self, fail_send: bool = False) -> None:
        """Initialize mock WebSocket."""
        self.accepted: bool = False
        self.closed: bool = False
        self.close_code: int | None = None
        self.close_reason: str | None = None
        self.fail_send: bool = fail_send
        self.sent_messages: list[str] = []
        self.incoming_messages: list[str] = []

    async def accept(self) -> None:
        """Record acceptance."""
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Record closure."""
        self.closed = True
        self.close_code = code
        self.close_reason = reason

    async def send_text(self, data: str) -> None:
        """Record sent text or raise exception if configured to fail."""
        if self.fail_send:
            raise ConnectionResetError("Client connection reset")
        self.sent_messages.append(data)

    async def send_json(self, data: dict[str, object]) -> None:
        """Record sent JSON."""
        await self.send_text(json.dumps(data))

    async def receive_text(self) -> str:
        """Pop next incoming message or raise WebSocketDisconnect."""
        if self.incoming_messages:
            return self.incoming_messages.pop(0)
        raise WebSocketDisconnect(code=1000)

    async def receive_json(self) -> dict[str, object]:
        """Pop and parse JSON."""
        text = await self.receive_text()
        parsed: object = json.loads(text) if text else {}
        return parsed if isinstance(parsed, dict) else {}


@pytest.mark.unit
@pytest.mark.issue_16
def test_jwt_create_and_verify_valid_token() -> None:
    """Validate creating and verifying a signed HS256 JWT access token."""
    payload = {"sub": "analyst-1", "role": "market_analyst", "tier": "premium"}
    token = create_access_token(payload, secret_key="test-secret-key", expires_in=1800)

    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    claims = verify_access_token(token, secret_key="test-secret-key")
    assert claims is not None
    assert claims["sub"] == "analyst-1"
    assert claims["role"] == "market_analyst"
    assert claims["tier"] == "premium"
    assert "exp" in claims
    assert "iat" in claims


@pytest.mark.unit
@pytest.mark.issue_16
def test_jwt_expired_token_rejection() -> None:
    """Validate that expired JWT tokens are rejected."""
    payload = {"sub": "expired-user"}
    # Token expired 10 seconds in the past
    expired_token = create_access_token(payload, secret_key="test-secret-key", expires_in=-10)

    claims = verify_access_token(expired_token, secret_key="test-secret-key")
    assert claims is None


@pytest.mark.unit
@pytest.mark.issue_16
def test_jwt_invalid_signature_and_tampered_payload() -> None:
    """Validate that tampered tokens and wrong secret keys are rejected."""
    token = create_access_token({"sub": "legit-user"}, secret_key="correct-key")

    # Wrong secret key
    assert verify_access_token(token, secret_key="wrong-key") is None

    # Tampered signature
    parts = token.split(".")
    tampered_sig = parts[0] + "." + parts[1] + ".invalidsignature"
    assert verify_access_token(tampered_sig, secret_key="correct-key") is None

    # Malformed tokens
    assert verify_access_token("", secret_key="correct-key") is None
    assert verify_access_token("not-a-jwt", secret_key="correct-key") is None
    assert verify_access_token("a.b", secret_key="correct-key") is None


@pytest.mark.unit
@pytest.mark.issue_16
async def test_connection_manager_connect_and_disconnect() -> None:
    """Validate ConnectionManager connect, disconnect, and tracking."""
    manager = ConnectionManager()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()

    assert len(manager.active_connections) == 0

    await manager.connect(ws1)
    assert ws1.accepted is True
    assert len(manager.active_connections) == 1

    await manager.connect(ws2)
    assert ws2.accepted is True
    assert len(manager.active_connections) == 2

    # Disconnect one
    manager.disconnect(ws1)
    assert len(manager.active_connections) == 1
    assert ws2 in manager.active_connections

    # Disconnect remaining
    manager.disconnect(ws2)
    assert len(manager.active_connections) == 0


@pytest.mark.unit
@pytest.mark.issue_16
async def test_connection_manager_send_personal_message() -> None:
    """Validate ConnectionManager direct messaging."""
    manager = ConnectionManager()
    ws = MockWebSocket()
    await manager.connect(ws)

    await manager.send_personal_message({"greeting": "welcome"}, ws)
    assert len(ws.sent_messages) == 1
    sent_dict = json.loads(ws.sent_messages[0])
    assert sent_dict["greeting"] == "welcome"


@pytest.mark.unit
@pytest.mark.issue_16
async def test_connection_manager_broadcast_and_prune_dead() -> None:
    """Validate ConnectionManager broadcast delivers to active clients and prunes failed ones."""
    manager = ConnectionManager()
    ws_ok_1 = MockWebSocket()
    ws_failing = MockWebSocket(fail_send=True)
    ws_ok_2 = MockWebSocket()

    await manager.connect(ws_ok_1)
    await manager.connect(ws_failing)
    await manager.connect(ws_ok_2)
    assert len(manager.active_connections) == 3

    # Broadcast message
    await manager.broadcast({"event": "ping_all"})

    # Dead connection was pruned automatically
    assert len(manager.active_connections) == 2
    assert ws_failing not in manager.active_connections
    assert ws_ok_1 in manager.active_connections
    assert ws_ok_2 in manager.active_connections

    # Both healthy connections received the broadcast
    assert len(ws_ok_1.sent_messages) == 1
    assert len(ws_ok_2.sent_messages) == 1


@pytest.mark.unit
@pytest.mark.issue_16
async def test_connection_manager_broadcast_alert() -> None:
    """Validate ConnectionManager.broadcast_alert formats and streams AlertItem events."""
    manager = ConnectionManager()
    ws = MockWebSocket()
    await manager.connect(ws)

    alert = AlertItem(
        id=uuid.uuid4(),
        symbol="AAPL",
        method="zscore",
        score=3.85,
        severity="high",
        details={"metric": "volume", "threshold": 3.0, "value": 150000000},
        timestamp=datetime.now(UTC),
    )

    await manager.broadcast_alert(alert)

    assert len(ws.sent_messages) == 1
    event_payload = json.loads(ws.sent_messages[0])
    assert event_payload["event"] == "alert"
    assert event_payload["data"]["symbol"] == "AAPL"
    assert event_payload["data"]["score"] == 3.85
    assert event_payload["data"]["severity"] == "high"


@pytest.mark.unit
@pytest.mark.issue_16
async def test_connection_manager_heartbeat() -> None:
    """Validate ConnectionManager heartbeat payload creation and background loop."""
    manager = ConnectionManager()
    ws = MockWebSocket()
    await manager.connect(ws)

    payload = manager.create_heartbeat_payload()
    assert payload["type"] == "ping"
    assert "timestamp" in payload

    await manager.broadcast_heartbeat()
    assert len(ws.sent_messages) == 1
    assert json.loads(ws.sent_messages[0])["type"] == "ping"

    # Start loop with very fast interval for test
    task = manager.start_heartbeat_loop(interval_seconds=0.05)
    await asyncio.sleep(0.12)
    manager.stop_heartbeat_loop()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert task.cancelled() or task.done()


@pytest.mark.unit
@pytest.mark.issue_16
async def test_handle_websocket_alerts_auth_success() -> None:
    """Validate WebSocket endpoint authenticates with valid token and handles pong."""
    manager = ConnectionManager()
    secret = "secret-key-123"
    valid_token = create_access_token({"sub": "trader-1"}, secret_key=secret)

    ws = MockWebSocket()
    ws.incoming_messages = [
        json.dumps({"type": "pong"}),
    ]

    await handle_websocket_alerts(ws, token=valid_token, manager=manager, secret_key=secret)

    assert ws.accepted is True
    assert ws.closed is False
    # After client closes (incoming messages exhausted), disconnected from manager
    assert len(manager.active_connections) == 0


@pytest.mark.unit
@pytest.mark.issue_16
async def test_handle_websocket_alerts_auth_failure() -> None:
    """Validate WebSocket endpoint rejects connection with code 1008 on invalid token."""
    manager = ConnectionManager()
    secret = "secret-key-123"

    # 1. Missing token
    ws_missing = MockWebSocket()
    await handle_websocket_alerts(ws_missing, token=None, manager=manager, secret_key=secret)
    assert ws_missing.accepted is False
    assert ws_missing.closed is True
    assert ws_missing.close_code == 1008

    # 2. Invalid token
    ws_invalid = MockWebSocket()
    await handle_websocket_alerts(
        ws_invalid, token="bad.token.here", manager=manager, secret_key=secret
    )
    assert ws_invalid.accepted is False
    assert ws_invalid.closed is True
    assert ws_invalid.close_code == 1008


@pytest.mark.unit
@pytest.mark.issue_16
async def test_asgi_websocket_alerts_route_integration() -> None:
    """Validate /ws/alerts route end-to-end through MarketIntelASGIApp."""
    app: MarketIntelASGIApp = create_app()
    secret = app.settings.secret_key
    valid_token = create_access_token({"sub": "test-analyst"}, secret_key=secret)

    # 1. Successful connection via ASGI
    received_events: list[dict[str, object]] = []

    async def mock_receive() -> dict[str, object]:
        # Return disconnect to cleanly exit the listen loop
        return {"type": "websocket.disconnect", "code": 1000}

    async def mock_send(event: dict[str, object]) -> None:
        received_events.append(event)

    scope: dict[str, object] = {
        "type": "websocket",
        "path": "/ws/alerts",
        "query_string": f"token={valid_token}".encode(),
    }

    await app(scope, mock_receive, mock_send)

    assert any(e.get("type") == "websocket.accept" for e in received_events)


@pytest.mark.unit
@pytest.mark.issue_16
async def test_asgi_websocket_alerts_route_unauthorized() -> None:
    """Validate /ws/alerts route through MarketIntelASGIApp rejects unauthenticated client."""
    app: MarketIntelASGIApp = create_app()
    received_events: list[dict[str, object]] = []

    async def mock_receive() -> dict[str, object]:
        return {"type": "websocket.disconnect", "code": 1000}

    async def mock_send(event: dict[str, object]) -> None:
        received_events.append(event)

    scope: dict[str, object] = {
        "type": "websocket",
        "path": "/ws/alerts",
        "query_string": b"token=invalid-token",
    }

    await app(scope, mock_receive, mock_send)

    # Must be closed with code 1008
    assert any(
        e.get("type") == "websocket.close" and e.get("code") == 1008 for e in received_events
    )


@pytest.mark.unit
@pytest.mark.issue_16
async def test_asgi_websocket_unknown_path() -> None:
    """Validate unknown WebSocket paths close with code 1000."""
    app: MarketIntelASGIApp = create_app()
    received_events: list[dict[str, object]] = []

    async def mock_receive() -> dict[str, object]:
        return {}

    async def mock_send(event: dict[str, object]) -> None:
        received_events.append(event)

    scope: dict[str, object] = {
        "type": "websocket",
        "path": "/ws/unknown",
        "query_string": b"",
    }

    await app(scope, mock_receive, mock_send)
    assert any(
        e.get("type") == "websocket.close" and e.get("code") == 1000 for e in received_events
    )


@pytest.mark.unit
@pytest.mark.issue_16
async def test_asgi_websocket_adapter_methods() -> None:
    """Validate ASGIWebSocketAdapter methods: send_json, receive_json, close."""
    sent: list[dict[str, object]] = []
    incoming: list[dict[str, object]] = [
        {"type": "websocket.send", "text": json.dumps({"status": "received"})},
    ]

    async def mock_send(event: dict[str, object]) -> None:
        sent.append(event)

    async def mock_receive() -> dict[str, object]:
        if incoming:
            return incoming.pop(0)
        return {"type": "websocket.disconnect", "code": 1000}

    adapter = ASGIWebSocketAdapter({}, mock_receive, mock_send)
    await adapter.accept()
    assert adapter.client_state == "connected"

    await adapter.send_json({"alert_id": "123"})
    assert any("alert_id" in str(e.get("text", "")) for e in sent)

    res_json = await adapter.receive_json()
    assert res_json.get("status") == "received"

    await adapter.close(code=1001, reason="Going away")
    assert adapter.client_state == "disconnected"
    assert any(e.get("code") == 1001 for e in sent)
