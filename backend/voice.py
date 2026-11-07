"""Bounded microphone transcription; recordings are never persisted by Hapic."""
from __future__ import annotations

import os

import httpx

from .runtime import RuntimeUnavailable

MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_TRANSCRIPT_LENGTH = 20_000
DEFAULT_TRANSCRIPTION_MODEL = "gpt-transcribe"
AUDIO_TYPES = {"audio/webm": "webm", "audio/mp4": "mp4", "audio/wav": "wav"}


def audio_format(data: bytes, content_type: str) -> tuple[str, str]:
    mime = content_type.split(";", 1)[0].strip().lower()
    extension = AUDIO_TYPES.get(mime)
    signatures = {
        "webm": data.startswith(b"\x1a\x45\xdf\xa3"),
        "mp4": len(data) >= 12 and data[4:8] == b"ftyp",
        "wav": len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE",
    }
    if not data or len(data) > MAX_AUDIO_BYTES or not signatures.get(extension):
        raise ValueError("Grabación no válida. Usa audio WebM, MP4 o WAV de hasta 8 MB.")
    return mime, extension


class VoiceTranscriber:
    async def transcribe(self, key: str | None, data: bytes, content_type: str) -> str:
        mime, extension = audio_format(data, content_type)
        if not key:
            raise RuntimeUnavailable("Configura la API key de OpenAI para usar el micrófono.")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=10), trust_env=False) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": "Bearer " + key},
                    data={"model": os.getenv("HAPIC_TRANSCRIPTION_MODEL", DEFAULT_TRANSCRIPTION_MODEL)},
                    files={"file": ("microphone." + extension, data, mime)},
                )
            if not response.is_success:
                raise RuntimeUnavailable(f"OpenAI Audio devolvió HTTP {response.status_code}. Revisa la credencial, el acceso al modelo y el saldo.")
            text = response.json().get("text")
            if not isinstance(text, str) or len(text) > MAX_TRANSCRIPT_LENGTH:
                raise RuntimeUnavailable("El proveedor no devolvió una transcripción válida. Intenta una grabación más breve.")
            if not text.strip():
                raise RuntimeUnavailable("No se reconoció voz. Acerca el micrófono y vuelve a grabar.")
            return text.strip()
        except (httpx.HTTPError, ValueError, AttributeError):
            # Never include provider bodies, request headers, or the recording in errors.
            raise RuntimeUnavailable("No se pudo transcribir el audio. La solicitud puede haberse facturado; vuelve a grabar cuando se restablezca la conexión.") from None
