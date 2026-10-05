"""FastAPI REST and WebSocket delivery module for market intelligence."""

from market_intel.api.app import app, create_app
from market_intel.api.websocket import (
    ConnectionManager,
    WebSocketDisconnect,
    connection_manager,
    handle_websocket_alerts,
)

__all__ = [
    "app",
    "create_app",
    "ConnectionManager",
    "connection_manager",
    "WebSocketDisconnect",
    "handle_websocket_alerts",
]
