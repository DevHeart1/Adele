"""Tests for ElevenLabs Scribe STT response parsing."""

import os
import sys

import pytest

backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, backend_path)

from voice.transcription import _elevenlabs_scribe, _extract_scribe_text


def test_extract_scribe_text_top_level():
    payload = {"text": "Hello ADELE", "words": []}
    assert _extract_scribe_text(payload) == "Hello ADELE"


def test_extract_scribe_text_from_transcripts():
    payload = {"transcripts": [{"text": "First"}, {"text": "Second"}]}
    assert _extract_scribe_text(payload) == "First Second"


def test_extract_scribe_text_from_words():
    payload = {
        "words": [
            {"text": "Hey", "type": "word"},
            {"text": "ADELE", "type": "word"},
            {"text": "(laughter)", "type": "audio_event"},
        ]
    }
    assert _extract_scribe_text(payload) == "Hey ADELE"


def test_extract_scribe_text_empty():
    assert _extract_scribe_text({}) == ""
    assert _extract_scribe_text("not a dict") == ""


@pytest.mark.asyncio
async def test_scribe_uses_english_by_default(monkeypatch):
    sent = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "Open Spotify"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, _url, *, headers, files, data):
            sent.update({"headers": headers, "files": files, "data": data})
            return FakeResponse()

    monkeypatch.delenv("ADELE_STT_LANGUAGE_CODE", raising=False)
    monkeypatch.setattr("voice.transcription.httpx.AsyncClient", lambda **_kwargs: FakeClient())

    assert await _elevenlabs_scribe(b"audio", "test-key") == "Open Spotify"
    assert sent["data"]["language_code"] == "eng"


@pytest.mark.asyncio
async def test_scribe_honors_explicit_language_override(monkeypatch):
    sent = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "Bonjour"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, _url, *, headers, files, data):
            sent.update({"headers": headers, "files": files, "data": data})
            return FakeResponse()

    monkeypatch.setenv("ADELE_STT_LANGUAGE_CODE", "fra")
    monkeypatch.setattr("voice.transcription.httpx.AsyncClient", lambda **_kwargs: FakeClient())

    assert await _elevenlabs_scribe(b"audio", "test-key") == "Bonjour"
    assert sent["data"]["language_code"] == "fra"
