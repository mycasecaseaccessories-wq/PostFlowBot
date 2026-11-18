from types import SimpleNamespace

import pytest

from app.core.exceptions import ConflictError
from app.services.routing_service import RoutingService


class FakeChannelService:
    def __init__(self, channel):
        self.channel = channel

    async def get_source(self, _channel_id):
        return self.channel

    async def get_target(self, _channel_id):
        return self.channel


@pytest.mark.asyncio
async def test_route_rejects_self_routing():
    channel = SimpleNamespace(
        telegram_chat_id=-1001234500001,
        is_active=True,
        posting_permission_status="verified",
    )
    service = RoutingService(
        None, FakeChannelService(channel), FakeChannelService(channel)
    )
    with pytest.raises(ConflictError, match="cannot route to itself"):
        await service.validate_route(1, 1)


@pytest.mark.asyncio
async def test_route_rejects_inactive_source():
    source = SimpleNamespace(telegram_chat_id=-1001234500001, is_active=False)
    target = SimpleNamespace(
        telegram_chat_id=-1001234500002,
        is_active=True,
        posting_permission_status="verified",
    )
    service = RoutingService(None, FakeChannelService(source), FakeChannelService(target))
    with pytest.raises(ConflictError, match="Enable the source"):
        await service.validate_route(1, 2)


@pytest.mark.asyncio
async def test_route_rejects_inactive_target():
    source = SimpleNamespace(telegram_chat_id=-1001234500001, is_active=True)
    target = SimpleNamespace(
        telegram_chat_id=-1001234500002,
        is_active=False,
        posting_permission_status="verified",
    )
    service = RoutingService(None, FakeChannelService(source), FakeChannelService(target))
    with pytest.raises(ConflictError, match="Enable the target"):
        await service.validate_route(1, 2)


@pytest.mark.asyncio
async def test_route_requires_verified_target_permission():
    source = SimpleNamespace(telegram_chat_id=-1001234500001, is_active=True)
    target = SimpleNamespace(
        telegram_chat_id=-1001234500002,
        is_active=True,
        posting_permission_status="unknown",
    )
    service = RoutingService(None, FakeChannelService(source), FakeChannelService(target))
    with pytest.raises(ConflictError, match="Verify target posting permission"):
        await service.validate_route(1, 2)
