"""Tests for ElevenLabs Scribe STT response parsing."""

import os
import sys

backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, backend_path)

from voice.transcription import _extract_scribe_text


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
