import base64
import logging
import struct
import math
import httpx
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

class SarvamAudioService:
    """
    Client for Sarvam AI Text-to-Speech API (`bulbul:v1`).
    Provides Hindi/Hinglish speech synthesis with audio fallback.
    """
    def __init__(self):
        self.api_key = settings.sarvam_api_key
        self.api_url = "https://api.sarvam.ai/text-to-speech"

    def synthesize_speech(self, text: str, speaker: str = "meera") -> tuple[str, bool]:
        """
        Synthesizes speech using Sarvam AI API.
        Returns: (data_uri_or_base64, is_live_sarvam_api_bool)
        """
        if self.api_key:
            try:
                headers = {
                    "api-subscription-key": self.api_key,
                    "Content-Type": "application/json"
                }
                payload = {
                    "inputs": [text[:500]],  # Sarvam limit per request
                    "target_language_code": "hi-IN",
                    "speaker": speaker,
                    "pitch": 0,
                    "pace": 1.0,
                    "loudness": 1.5,
                    "speech_sample_rate": 8000,
                    "enable_preprocessing": True,
                    "model": "bulbul:v1"
                }
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(self.api_url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        audios = data.get("audios", [])
                        if audios and len(audios) > 0:
                            b64 = audios[0]
                            return f"data:audio/wav;base64,{b64}", True
            except Exception as e:
                logger.warning(f"Sarvam AI TTS call failed: {e}. Generating fallback tone.")

        # Fallback: Generate lightweight valid WAV data URI with soft chime
        fallback_wav = self._generate_chime_wav()
        b64_str = base64.b64encode(fallback_wav).decode("ascii")
        return f"data:audio/wav;base64,{b64_str}", False

    def _generate_chime_wav(self, duration_s: float = 1.2, sample_rate: int = 8000) -> bytes:
        """Generates a pleasant 2-tone chime PCM WAV file in pure Python (no external deps)."""
        num_samples = int(duration_s * sample_rate)
        pcm_data = bytearray()

        freq1, freq2 = 523.25, 659.25  # C5 to E5 harmonic chord
        for i in range(num_samples):
            t = i / sample_rate
            decay = math.exp(-3.0 * t)
            sample_val = 0.5 * math.sin(2 * math.pi * freq1 * t) + 0.5 * math.sin(2 * math.pi * freq2 * t)
            sample_val *= decay
            int_val = int(sample_val * 32767.0)
            int_val = max(-32768, min(32767, int_val))
            pcm_data.extend(struct.pack("<h", int_val))

        # 44-byte WAV header
        header = bytearray()
        header.extend(b"RIFF")
        header.extend(struct.pack("<I", 36 + len(pcm_data)))
        header.extend(b"WAVE")
        header.extend(b"fmt ")
        header.extend(struct.pack("<I", 16))  # Subchunk1Size (16 for PCM)
        header.extend(struct.pack("<H", 1))   # AudioFormat (1 = PCM)
        header.extend(struct.pack("<H", 1))   # NumChannels (1 = Mono)
        header.extend(struct.pack("<I", sample_rate))  # SampleRate
        header.extend(struct.pack("<I", sample_rate * 2))  # ByteRate (SampleRate * NumChannels * BitsPerSample/8)
        header.extend(struct.pack("<H", 2))   # BlockAlign (NumChannels * BitsPerSample/8)
        header.extend(struct.pack("<H", 16))  # BitsPerSample (16 bits)
        header.extend(b"data")
        header.extend(struct.pack("<I", len(pcm_data)))

        return bytes(header + pcm_data)

sarvam_service = SarvamAudioService()
