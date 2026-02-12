"""
Unit tests for WebSocket connection manager and message handling.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from websocket_manager import ConnectionManager, parse_control_message
from models import MessageType


@pytest.fixture
def manager():
    return ConnectionManager()


def _make_ws():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect(manager):
    """Test new connection is registered."""
    ws = _make_ws()
    await manager.connect(ws)

    assert manager.client_count == 1
    ws.accept.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect(manager):
    """Test disconnection removes the connection."""
    ws = _make_ws()
    await manager.connect(ws)
    manager.disconnect(ws)

    assert manager.client_count == 0


@pytest.mark.asyncio
async def test_broadcast(manager):
    """Test message is sent to all connected clients."""
    ws1 = _make_ws()
    ws2 = _make_ws()
    await manager.connect(ws1)
    await manager.connect(ws2)

    message = {"type": "status", "status": "test"}
    await manager.broadcast(message)

    expected = json.dumps(message)
    ws1.send_text.assert_called_once_with(expected)
    ws2.send_text.assert_called_once_with(expected)


@pytest.mark.asyncio
async def test_broadcast_removes_dead_connections(manager):
    """Test that broken connections are removed during broadcast."""
    ws_good = _make_ws()
    ws_dead = _make_ws()
    ws_dead.send_text = AsyncMock(side_effect=Exception("Connection lost"))

    await manager.connect(ws_good)
    await manager.connect(ws_dead)

    assert manager.client_count == 2

    await manager.broadcast({"type": "test"})

    # Dead connection should be removed
    assert manager.client_count == 1


@pytest.mark.asyncio
async def test_send_personal(manager):
    """Test sending a message to a specific client."""
    ws = _make_ws()
    await manager.connect(ws)

    message = {"type": "status", "status": "hello"}
    await manager.send_personal(ws, message)

    ws.send_text.assert_called_with(json.dumps(message))


@pytest.mark.asyncio
async def test_parse_control_message_valid():
    """Test parsing a valid control message."""
    data = json.dumps({"type": "control", "action": "start"})
    result = await parse_control_message(data)

    assert result is not None
    assert result.action == "start"


@pytest.mark.asyncio
async def test_parse_control_message_stop():
    """Test parsing a stop control message."""
    data = json.dumps({"type": "control", "action": "stop"})
    result = await parse_control_message(data)

    assert result is not None
    assert result.action == "stop"


@pytest.mark.asyncio
async def test_parse_control_message_invalid_json():
    """Test parsing invalid JSON returns None."""
    result = await parse_control_message("not json")
    assert result is None


@pytest.mark.asyncio
async def test_parse_control_message_wrong_type():
    """Test parsing a non-control message returns None."""
    data = json.dumps({"type": "transcript", "text": "hello"})
    result = await parse_control_message(data)
    assert result is None
