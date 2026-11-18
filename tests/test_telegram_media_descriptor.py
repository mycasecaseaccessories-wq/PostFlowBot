from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.telegram.listener as listener
from app.telegram.listener import MessageListenerService


@pytest.fixture
def patch_file_id(monkeypatch):
    monkeypatch.setattr(listener.utils, "pack_bot_file_id", lambda media: f"packed:{media.id}")


def test_photo_descriptor_keeps_dimensions_and_file_reference(monkeypatch, patch_file_id):
    photo = SimpleNamespace(
        id=101,
        sizes=[SimpleNamespace(size=10, w=320, h=240), SimpleNamespace(size=20, w=1280, h=960)],
    )
    message = SimpleNamespace(id=1, photo=photo, document=None)
    descriptor = MessageListenerService._media_descriptor(message)
    assert descriptor is not None
    assert descriptor.telegram_file_id == "packed:101"
    assert descriptor.telegram_file_unique_id == "telethon:photo:101"
    assert descriptor.media_type == "photo"
    assert (descriptor.width, descriptor.height) == (1280, 960)


def test_video_and_voice_document_classification(monkeypatch, patch_file_id):
    class FakeVideoAttribute:
        def __init__(self):
            self.w, self.h, self.duration = 1920, 1080, 18

    class FakeAudioAttribute:
        def __init__(self, voice):
            self.voice, self.duration = voice, 7

    class FakeFilenameAttribute:
        file_name = "clip.mp4"

    monkeypatch.setattr(listener, "DocumentAttributeVideo", FakeVideoAttribute)
    monkeypatch.setattr(listener, "DocumentAttributeAudio", FakeAudioAttribute)
    monkeypatch.setattr(listener, "DocumentAttributeFilename", FakeFilenameAttribute)

    video_document = SimpleNamespace(
        id=202, size=4096, mime_type="video/mp4",
        attributes=[FakeFilenameAttribute(), FakeVideoAttribute()],
    )
    video_message = SimpleNamespace(id=2, photo=None, document=video_document)
    video = MessageListenerService._media_descriptor(video_message)
    assert video is not None
    assert video.media_type == "video"
    assert video.original_file_name == "clip.mp4"
    assert (video.width, video.height, video.duration) == (1920, 1080, 18)

    voice_document = SimpleNamespace(
        id=303, size=512, mime_type="audio/ogg",
        attributes=[FakeAudioAttribute(True)],
    )
    voice_message = SimpleNamespace(id=3, photo=None, document=voice_document)
    voice = MessageListenerService._media_descriptor(voice_message)
    assert voice is not None
    assert voice.media_type == "voice"
    assert voice.duration == 7


def test_generic_document_and_image_document_classification(patch_file_id):
    pdf = SimpleNamespace(id=404, size=100, mime_type="application/pdf", attributes=[])
    document = MessageListenerService._media_descriptor(
        SimpleNamespace(id=4, photo=None, document=pdf)
    )
    assert document is not None and document.media_type == "document"

    image = SimpleNamespace(id=405, size=100, mime_type="image/webp", attributes=[])
    image_descriptor = MessageListenerService._media_descriptor(
        SimpleNamespace(id=5, photo=None, document=image)
    )
    assert image_descriptor is not None
    assert image_descriptor.media_type == "photo"
    assert image_descriptor.mime_type == "image/webp"
