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


@pytest.mark.asyncio
async def test_route_filter_update_changes_only_requested_values():
    class FakeRepository:
        def __init__(self):
            self.route = SimpleNamespace(
                id=9, remove_usernames=False, remove_links=False,
                remove_keywords=None, is_active=True,
            )
            self.saved = None

        async def get(self, route_id):
            return self.route if route_id == 9 else None

        async def save(self, values, route_id):
            self.saved = dict(values)
            for key, value in values.items():
                setattr(self.route, key, value)
            return self.route

    repository = FakeRepository()
    service = RoutingService(repository, None, None)
    route = await service.update_route_filters(
        9, 42, remove_usernames=True, remove_keywords="spam, scam",
        update_keywords=True,
    )
    assert route.remove_usernames is True
    assert route.remove_links is False
    assert route.remove_keywords == "spam, scam"
    assert repository.saved == {
        "remove_usernames": True,
        "remove_keywords": "spam, scam",
    }


@pytest.mark.asyncio
async def test_route_filter_update_can_clear_keyword_list():
    class FakeRepository:
        def __init__(self):
            self.route = SimpleNamespace(id=10, remove_keywords="spam")

        async def get(self, route_id):
            return self.route

        async def save(self, values, route_id):
            for key, value in values.items():
                setattr(self.route, key, value)
            return self.route

    service = RoutingService(FakeRepository(), None, None)
    route = await service.update_route_filters(
        10, 42, remove_keywords=None, update_keywords=True
    )
    assert route.remove_keywords is None
