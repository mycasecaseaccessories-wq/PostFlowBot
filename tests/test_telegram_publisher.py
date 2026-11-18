from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.publishing_worker import PermanentPublishError, RetryablePublishError
from app.telegram.publisher import TelegramPublisher


class FakeClient:
    def __init__(self):
        self.connected = True
        self.authorized = True
        self.calls = []

    def is_connected(self):
        return self.connected

    async def is_user_authorized(self):
        return self.authorized

    async def send_message(self, destination, text, **kwargs):
        self.calls.append(("text", destination, text, kwargs))
        return SimpleNamespace(id=101)

    async def send_file(self, destination, files, **kwargs):
        self.calls.append(("media", destination, files, kwargs))
        if isinstance(files, list):
            return [SimpleNamespace(id=201), SimpleNamespace(id=202)]
        return SimpleNamespace(id=201)


class FakeStorage:
    def __init__(self, root: Path):
        self.root = root

    def resolve(self, key: str) -> Path:
        return self.root / key


@pytest.mark.asyncio
async def test_publisher_sends_text_and_returns_message_id(tmp_path: Path):
    client = FakeClient()
    publisher = TelegramPublisher(client, FakeStorage(tmp_path))
    payload = SimpleNamespace(
        destination_chat_id=-100123,
        text="Hello",
        media=(),
    )
    assert await publisher.publish(payload) == 101
    assert client.calls[0][0:3] == ("text", -100123, "Hello")


@pytest.mark.asyncio
async def test_publisher_sends_single_stored_media_with_caption(tmp_path: Path):
    client = FakeClient()
    (tmp_path / "photo.jpg").write_bytes(b"image")
    publisher = TelegramPublisher(client, FakeStorage(tmp_path))
    media = SimpleNamespace(storage_backend="local", storage_key="photo.jpg")
    payload = SimpleNamespace(
        destination_chat_id=-100123, text="Caption", media=(media,)
    )
    assert await publisher.publish(payload) == 201
    call = client.calls[0]
    assert call[0] == "media"
    assert call[2] == str(tmp_path / "photo.jpg")
    assert call[3]["caption"] == "Caption"


@pytest.mark.asyncio
async def test_publisher_sends_album_as_one_telegram_media_group(tmp_path: Path):
    client = FakeClient()
    (tmp_path / "one.jpg").write_bytes(b"one")
    (tmp_path / "two.jpg").write_bytes(b"two")
    publisher = TelegramPublisher(client, FakeStorage(tmp_path))
    media = (
        SimpleNamespace(storage_backend="local", storage_key="one.jpg"),
        SimpleNamespace(storage_backend="local", storage_key="two.jpg"),
    )
    payload = SimpleNamespace(
        destination_chat_id=-100123, text="Album caption", media=media
    )
    assert await publisher.publish(payload) == 201
    call = client.calls[0]
    assert call[0] == "media"
    assert call[2] == [str(tmp_path / "one.jpg"), str(tmp_path / "two.jpg")]


@pytest.mark.asyncio
async def test_publisher_refuses_missing_media_without_sending(tmp_path: Path):
    client = FakeClient()
    publisher = TelegramPublisher(client, FakeStorage(tmp_path))
    media = SimpleNamespace(storage_backend="local", storage_key="missing.jpg")
    payload = SimpleNamespace(destination_chat_id=-100123, text="", media=(media,))
    with pytest.raises(PermanentPublishError, match="missing"):
        await publisher.publish(payload)
    assert client.calls == []


@pytest.mark.asyncio
async def test_publisher_refuses_unauthorized_client(tmp_path: Path):
    client = FakeClient()
    client.authorized = False
    publisher = TelegramPublisher(client, FakeStorage(tmp_path))
    payload = SimpleNamespace(destination_chat_id=-100123, text="Hello", media=())
    with pytest.raises(PermanentPublishError, match="authorized"):
        await publisher.publish(payload)
    assert client.calls == []
