# Issue 16: WebSocket streaming for real-time market alerts

**Branch:** `feature/issue-16-websocket-streaming`  
**Status:** In Progress (Ready for Verification)  
**PR:** TBD  
**Milestone:** M4 — Orchestration & Delivery Layer  

---

## Objective

Build `src/market_intel/api/websocket.py` and integrate it into `src/market_intel/api/app.py` to provide a resilient real-time WebSocket streaming endpoint (`/ws/alerts`) for broadcasting anomaly detection alerts to connected clients, featuring connection management, JWT-based query authentication, periodic 30-second heartbeat ping/pong keepalive, and unit tests under `@pytest.mark.issue_16`.

---

## Acceptance Criteria

- [x] **WebSocket `/ws/alerts` Endpoint**: Stream anomaly alerts as JSON events in real-time to connected clients.
- [x] **Connection Manager**: Manage active client connections with broadcast, direct messaging, and robust handling of disconnected clients.
- [x] **Heartbeat Ping/Pong**: Periodic heartbeat (ping/pong every 30 seconds) to detect and purge stale connections.
- [x] **JWT Authentication**: Validate JWT token provided in connection query parameter (`?token=...`), rejecting unauthenticated/expired connections with code 1008 (Policy Violation).
- [x] **Unit & Integration Tests**: Comprehensive tests using `pytest -m issue_16` covering connection management, broadcast, JWT auth validation, heartbeat keepalive, and WebSocket event transmission.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=16 NAME=websocket-streaming
```

### 2. Dependencies & Security Configuration
- **File**: `pyproject.toml`
  - Add `pyjwt>=2.8.0` and `websockets>=12.0` to `[project.optional-dependencies] orchestration`.
  - Verify `issue_16` test marker is registered.
- **File**: `src/market_intel/core/config.py`
  - Ensure JWT settings: `jwt_algorithm: str = "HS256"`, `jwt_expiration_seconds: int = 3600`.
- **File**: `src/market_intel/core/security.py`
  - Implement RFC 7519 standard HS256 JWT encoding and decoding helpers:
    - `create_access_token(payload: dict[str, object], secret_key: str | None = None, expires_in: int = 3600) -> str`
    - `verify_access_token(token: str, secret_key: str | None = None) -> dict[str, object] | None`
    - Dual-engine implementation: uses `pyjwt` if installed, with native standard library fallback (`hmac` + `hashlib` + `base64`) ensuring tests run reliably offline.
- **File**: `src/market_intel/core/__init__.py`
  - Re-export `create_access_token` and `verify_access_token`.

### 3. Connection Manager & WebSocket Delivery
- **File**: `src/market_intel/api/websocket.py`
  - Implement `ConnectionManager`:
    - `connect(websocket)`: Accept and register client connection.
    - `disconnect(websocket)`: Safely unregister client connection.
    - `broadcast(message: dict[str, object] | str)`: Broadcast message to all connected clients concurrently, safely pruning disconnected sockets.
    - `send_personal_message(message: dict[str, object] | str, websocket)`: Send direct message to a client.
    - `broadcast_alert(alert: AlertItem | dict[str, object])`: Format and broadcast anomaly alert JSON events (`{"event": "alert", "data": ...}`).
    - `create_heartbeat_payload()`: Return standard ping heartbeat payload (`{"type": "ping", "timestamp": ...}`).
  - Implement WebSocket handler:
    - Extracts `token` query param and validates with `verify_access_token`.
    - Closes with code 1008 if token is missing or invalid.
    - Handles incoming pong messages and client disconnects.
- **File**: `src/market_intel/api/app.py`
  - Mount `/ws/alerts` on FastAPI and ASGI app.
  - Implement ASGI WebSocket scope handler (`websocket.connect`, `websocket.receive`, `websocket.send`, `websocket.disconnect`).
  - Expose singleton `connection_manager`.
- **File**: `src/market_intel/api/__init__.py`
  - Re-export `ConnectionManager`, `connection_manager`, and WebSocket utilities.

### 4. Test Suite
- **File**: `tests/unit/test_websocket.py`
  - Marked with `@pytest.mark.unit` and `@pytest.mark.issue_16`.
  - Test `ConnectionManager` lifecycle: connect, disconnect, active count.
  - Test `ConnectionManager.broadcast` to multiple clients and silent pruning on dropped connections.
  - Test `ConnectionManager.send_personal_message`.
  - Test JWT creation, verification, expiration, and invalid signature rejection.
  - Test heartbeat ping payload creation and pong handling.
  - Test WebSocket `/ws/alerts` via ASGI client:
    - Connection accepted with valid token.
    - Connection closed (code 1008) with missing or invalid token.
    - Alert event broadcasting received by connected client.

### 5. Verification
```bash
make test-issue ID=16
make check
```

### 6. Git & Finish
```bash
make finish-issue ID=16 MSG="feat(delivery): implement WebSocket streaming for real-time market alerts"
```
