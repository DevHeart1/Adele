"""
ADELE — Streamed TTS via Google Cloud Text-to-Speech (Neural2)
==================================================================
Splits response text into sentences, synthesizes each sentence
concurrently, and yields audio chunks in order so the first sentence
plays while later ones are still synthesizing.

Usage:
    from voice.tts import TTSEngine

    tts = TTSEngine()
    async for chunk in tts.stream_synthesize("Hello! How can I help?"):
        # chunk is a TTSChunk with .audio (bytes), .seq (int), .final (bool)
        await ws.send(chunk.to_ws_message())
"""

import asyncio
import base64
import json
import re
import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional, Union
from functools import partial

import httpx

print = partial(print, flush=True)


def tts_backend() -> str:
    """Prefer ElevenLabs when configured unless ADELE_TTS_PROVIDER forces Google."""
    explicit = os.environ.get("ADELE_TTS_PROVIDER", "").strip().lower()
    if explicit in ("google", "elevenlabs"):
        return explicit
    if os.environ.get("ELEVENLABS_API_KEY", "").strip():
        return "elevenlabs"
    return "google"


# ═══════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════

# Default Neural2 voice — natural, mid-cost ($16/1M chars)
DEFAULT_VOICE = os.environ.get("ADELE_TTS_VOICE", "en-US-Neural2-J")
DEFAULT_LANGUAGE = os.environ.get("ADELE_TTS_LANGUAGE", "en-US")
DEFAULT_SPEAKING_RATE = float(os.environ.get("ADELE_TTS_SPEED", "1.05"))

# Audio encoding: OGG_OPUS is compact and plays natively in Chromium
AUDIO_ENCODING = "OGG_OPUS"

# Max characters per synthesis call (Google TTS limit is 5000)
MAX_CHARS_PER_CALL = 4800

# Concurrency limit for parallel sentence synthesis
MAX_CONCURRENT_SYNTH = 4


# ═══════════════════════════════════════════════════════════════
#  Data Types
# ═══════════════════════════════════════════════════════════════

@dataclass
class TTSChunk:
    """A single chunk of synthesized audio."""
    audio: bytes        # Raw audio bytes (OGG/OPUS or MP3)
    seq: int            # Sequence number (0-based)
    final: bool         # True if this is the last chunk
    text: str           # The sentence that was synthesized
    format: str = "ogg" # "ogg" (Google) or "mp3" (ElevenLabs)

    def to_ws_message(self) -> str:
        """Serialize to a JSON WebSocket message."""
        return json.dumps({
            "type": "tts_chunk",
            "data": base64.b64encode(self.audio).decode("ascii"),
            "seq": self.seq,
            "final": self.final,
            "format": self.format,
        })


# ═══════════════════════════════════════════════════════════════
#  Text Preparation
# ═══════════════════════════════════════════════════════════════

# Markdown patterns to strip before sending to TTS
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"\*(.+?)\*")
_MD_CODE = re.compile(r"`(.+?)`")
_MD_LINK = re.compile(r"\[(.+?)\]\(.+?\)")
_MD_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_MD_NUMBERED = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)

# Sentence boundary — split on . ! ? followed by space or end
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def prepare_for_speech(text: str, display_type: str = "text") -> str:
    """
    Clean and optionally truncate text for spoken output.

    Args:
        text: Raw response text (may contain markdown).
        display_type: "pill" for short responses, "card"/"rich" for long ones.

    Returns:
        Clean spoken text ready for TTS.
    """
    if not text:
        return ""

    # Strip conversation mode markers
    text = text.replace("[CONVERSATION_MODE_ON]", "").replace("[CONVERSATION_MODE_OFF]", "")

    # Strip markdown formatting
    text = _MD_BOLD.sub(r"\1", text)
    text = _MD_ITALIC.sub(r"\1", text)
    text = _MD_CODE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BULLET.sub("", text)
    text = _MD_NUMBERED.sub("", text)

    # Collapse whitespace
    text = re.sub(r"\n{2,}", ". ", text)
    text = re.sub(r"\n", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip()

    # For long responses (card/rich), truncate to ~3 sentences for speech
    if display_type in ("card", "rich") and len(text) > 300:
        sentences = _SENTENCE_SPLIT.split(text)
        text = " ".join(sentences[:3])
        if not text.endswith((".", "!", "?")):
            text += "."

    return text


def split_sentences(text: str) -> list[str]:
    """Split text into sentence-sized chunks for streaming synthesis."""
    if not text:
        return []

    sentences = _SENTENCE_SPLIT.split(text)
    result = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # If adding this sentence would exceed the limit, flush current
        if current and len(current) + len(sentence) + 1 > MAX_CHARS_PER_CALL:
            result.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip() if current else sentence

    if current:
        result.append(current)

    # If nothing was split (single short sentence), return as-is
    if not result and text.strip():
        result = [text.strip()]

    return result


# ═══════════════════════════════════════════════════════════════
#  TTS Engine
# ═══════════════════════════════════════════════════════════════

class TTSEngine:
    """
    Async streamed TTS via Google Cloud Text-to-Speech.

    Lazily initializes the Google TTS client on first use.
    Synthesizes sentences concurrently and yields audio chunks
    in order for streaming playback.
    """

    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        language: str = DEFAULT_LANGUAGE,
        speaking_rate: float = DEFAULT_SPEAKING_RATE,
    ):
        self.voice_name = voice
        self.language_code = language
        self.speaking_rate = speaking_rate
        self._client = None
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    def _get_client(self):
        """Lazily create the Google TTS client."""
        if self._client is None:
            try:
                from google.cloud import texttospeech
                self._client = texttospeech.TextToSpeechAsyncClient()
                print("[TTS] ✓ Google Cloud TTS client initialized")
            except ImportError:
                print("[TTS] ⚠ google-cloud-texttospeech not installed — TTS disabled")
                self._enabled = False
                return None
            except Exception as e:
                print(f"[TTS] ⚠ Failed to initialize TTS client: {e}")
                self._enabled = False
                return None
        return self._client

    async def _synthesize_one(self, text: str) -> Optional[bytes]:
        """Synthesize a single text segment. Returns audio bytes or None."""
        client = self._get_client()
        if not client:
            return None

        try:
            from google.cloud import texttospeech

            request = texttospeech.SynthesizeSpeechRequest(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code=self.language_code,
                    name=self.voice_name,
                ),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.OGG_OPUS,
                    speaking_rate=self.speaking_rate,
                    pitch=0.0,
                ),
            )

            response = await client.synthesize_speech(request=request)
            return response.audio_content

        except Exception as e:
            print(f"[TTS] ⚠ Synthesis error: {e}")
            return None

    async def synthesize(self, text: str) -> Optional[bytes]:
        """Synthesize full text as a single audio blob."""
        if not self._enabled or not text:
            return None
        cleaned = prepare_for_speech(text)
        if not cleaned:
            return None
        return await self._synthesize_one(cleaned)

    async def stream_synthesize(
        self,
        text: str,
        display_type: str = "text",
    ) -> AsyncIterator[TTSChunk]:
        """
        Stream-synthesize text sentence by sentence.

        Kicks off synthesis for all sentences concurrently (up to
        MAX_CONCURRENT_SYNTH), then yields audio chunks in order
        so the first sentence can play while later ones are still
        being synthesized.

        Args:
            text: Raw response text (may contain markdown).
            display_type: "pill", "card", "rich" — affects truncation.

        Yields:
            TTSChunk objects with audio bytes, sequence number, and final flag.
        """
        if not self._enabled:
            return

        cleaned = prepare_for_speech(text, display_type)
        if not cleaned:
            return

        sentences = split_sentences(cleaned)
        if not sentences:
            return

        print(f"[TTS] 🔊 Streaming {len(sentences)} sentence(s), "
              f"{len(cleaned)} chars, voice={self.voice_name}")

        # Launch all synthesis tasks concurrently (with semaphore)
        sem = asyncio.Semaphore(MAX_CONCURRENT_SYNTH)

        async def _synth_with_limit(s: str) -> Optional[bytes]:
            async with sem:
                return await self._synthesize_one(s)

        tasks = [asyncio.create_task(_synth_with_limit(s)) for s in sentences]

        # Yield results in order as they complete
        for seq, (task, sentence_text) in enumerate(zip(tasks, sentences)):
            try:
                audio = await task
                if audio:
                    yield TTSChunk(
                        audio=audio,
                        seq=seq,
                        final=(seq == len(sentences) - 1),
                        text=sentence_text,
                        format="ogg",
                    )
            except asyncio.CancelledError:
                # Cancelled by interrupt — stop yielding
                for remaining_task in tasks[seq + 1:]:
                    remaining_task.cancel()
                return
            except Exception as e:
                print(f"[TTS] ⚠ Sentence {seq} failed: {e}")
                continue

        print("[TTS] ✓ Stream complete")

    async def speak_ack(self, ack_text: str) -> Optional[bytes]:
        """
        Synthesize a very short acknowledgment (e.g. "On it!").
        Returns raw audio bytes for immediate playback.
        """
        if not self._enabled or not ack_text:
            return None
        return await self._synthesize_one(ack_text)


class ElevenLabsTTSEngine:
    """Text-to-speech via ElevenLabs HTTP API (MP3 chunks)."""

    def __init__(self):
        self.api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        self.voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM").strip()
        self.model_id = os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_v3").strip()
        self._enabled = bool(self.api_key and self.voice_id)
        timeout_s = os.environ.get("ADELE_TTS_TIMEOUT", "120")
        self._timeout = float(timeout_s or 120)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    async def _synthesize_one(self, text: str) -> Optional[bytes]:
        if not self._enabled or not text:
            return None
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        params = {"output_format": "mp3_44100_128"}
        headers = {
            "xi-api-key": self.api_key,
            "accept": "audio/mpeg",
            "Content-Type": "application/json",
        }
        body = {"text": text, "model_id": self.model_id}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(url, params=params, json=body, headers=headers)
                r.raise_for_status()
                return r.content
        except Exception as e:
            print(f"[TTS ElevenLabs] ⚠ Synthesis error: {e}")
            return None

    async def synthesize(self, text: str) -> Optional[bytes]:
        if not self._enabled or not text:
            return None
        cleaned = prepare_for_speech(text)
        if not cleaned:
            return None
        return await self._synthesize_one(cleaned)

    async def stream_synthesize(
        self,
        text: str,
        display_type: str = "text",
    ) -> AsyncIterator[TTSChunk]:
        if not self._enabled:
            return

        cleaned = prepare_for_speech(text, display_type)
        if not cleaned:
            return

        sentences = split_sentences(cleaned)
        if not sentences:
            return

        print(
            f"[TTS ElevenLabs] 🔊 Streaming {len(sentences)} sentence(s), "
            f"{len(cleaned)} chars, voice={self.voice_id}, model={self.model_id}",
        )

        sem = asyncio.Semaphore(MAX_CONCURRENT_SYNTH)

        async def _synth_with_limit(s: str) -> Optional[bytes]:
            async with sem:
                return await self._synthesize_one(s)

        tasks = [asyncio.create_task(_synth_with_limit(s)) for s in sentences]

        for seq, (task, sentence_text) in enumerate(zip(tasks, sentences)):
            try:
                audio = await task
                if audio:
                    yield TTSChunk(
                        audio=audio,
                        seq=seq,
                        final=(seq == len(sentences) - 1),
                        text=sentence_text,
                        format="mp3",
                    )
            except asyncio.CancelledError:
                for remaining_task in tasks[seq + 1:]:
                    remaining_task.cancel()
                return
            except Exception as e:
                print(f"[TTS ElevenLabs] ⚠ Sentence {seq} failed: {e}")
                continue

        print("[TTS ElevenLabs] ✓ Stream complete")

    async def speak_ack(self, ack_text: str) -> Optional[bytes]:
        if not self._enabled or not ack_text:
            return None
        return await self._synthesize_one(ack_text)


# ═══════════════════════════════════════════════════════════════
#  Singleton
# ═══════════════════════════════════════════════════════════════

_tts_engine: Optional[Union[TTSEngine, ElevenLabsTTSEngine]] = None


def get_tts_engine() -> Union[TTSEngine, ElevenLabsTTSEngine]:
    """Google Cloud or ElevenLabs TTS singleton based on ADELE_TTS_PROVIDER / keys."""
    global _tts_engine
    if _tts_engine is None:
        use_el = tts_backend() == "elevenlabs"
        if use_el:
            el = ElevenLabsTTSEngine()
            if el.enabled:
                _tts_engine = el
                print(
                    f"[TTS] ElevenLabs TTS ready "
                    f"(voice={el.voice_id}, model={el.model_id})"
                )
            else:
                print(
                    "[TTS] ElevenLabs selected but missing ELEVENLABS_API_KEY or "
                    "ELEVENLABS_VOICE_ID — falling back to Google Cloud TTS",
                )
                _tts_engine = TTSEngine()
        else:
            _tts_engine = TTSEngine()
            print(f"[TTS] Google Cloud TTS ready (voice={_tts_engine.voice_name})")
    return _tts_engine


def reset_tts_engine() -> None:
    """Clear cached engine (e.g. after credential refresh)."""
    global _tts_engine
    _tts_engine = None
