"""
ADELE — Speech-to-text (Google Web Speech vs ElevenLabs Scribe).
"""

from __future__ import annotations

import asyncio
import io
import os
from functools import partial

import httpx
import speech_recognition as sr

print = partial(print, flush=True)

ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"


def stt_backend() -> str:
    """Prefer ElevenLabs Scribe when a key exists unless explicitly overridden."""
    explicit = os.environ.get("ADELE_STT_PROVIDER", "").strip().lower()
    if explicit in ("google", "elevenlabs"):
        return explicit
    if os.environ.get("ELEVENLABS_API_KEY", "").strip():
        return "elevenlabs"
    return "google"


def _extract_scribe_text(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""

    text = (payload.get("text") or "").strip()
    if text:
        return text

    txs = payload.get("transcripts")
    if isinstance(txs, list) and txs:
        parts = [(t.get("text") or "").strip() for t in txs if isinstance(t, dict)]
        joined = " ".join(p for p in parts if p).strip()
        if joined:
            return joined

    words = payload.get("words")
    if isinstance(words, list) and words:
        parts = []
        for word in words:
            if not isinstance(word, dict):
                continue
            if word.get("type") not in (None, "", "word"):
                continue
            piece = (word.get("text") or "").strip()
            if piece:
                parts.append(piece)
        return " ".join(parts).strip()

    return ""


async def _elevenlabs_scribe(wav_bytes: bytes, api_key: str) -> str:
    model_id = (os.environ.get("ADELE_STT_MODEL_ID") or "scribe_v2").strip()
    lang = (os.environ.get("ADELE_STT_LANGUAGE_CODE") or "").strip()

    data = {"model_id": model_id, "tag_audio_events": "false", "timestamps_granularity": "none"}
    if lang:
        data["language_code"] = lang

    headers = {"xi-api-key": api_key}
    timeout = float(os.environ.get("ADELE_STT_TIMEOUT", "120") or 120)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            ELEVENLABS_STT_URL,
            headers=headers,
            files={"file": ("speech.wav", wav_bytes, "audio/wav")},
            data=data,
        )
        resp.raise_for_status()
        body = resp.json()

    text = _extract_scribe_text(body if isinstance(body, dict) else {})
    if text:
        return text
    raise sr.UnknownValueError()


async def transcribe_wav_bytes(wav_bytes: bytes, recognizer: sr.Recognizer) -> str:
    """Transcribe a mono 16‑bit PCM WAV in memory."""
    backend = stt_backend()
    if backend == "elevenlabs":
        key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not key:
            print("[STT] ADELE_STT_PROVIDER=elevenlabs but ELEVENLABS_API_KEY empty — using Google.")
        else:
            try:
                return await _elevenlabs_scribe(wav_bytes, key)
            except httpx.HTTPError as exc:
                print(f"[STT] ElevenLabs error: {exc}")
                raise sr.RequestError(str(exc)) from exc

    loop = asyncio.get_running_loop()

    def _google_sync() -> str:
        with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
            audio_data = recognizer.record(source)
        return recognizer.recognize_google(audio_data)

    return await loop.run_in_executor(None, _google_sync)
