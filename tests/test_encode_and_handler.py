import base64
import io
import struct

import numpy as np
import pytest
import soundfile as sf

import handler
from tts_core import FakeEngine, encode_audio

TONE = (0.3 * np.sin(2 * np.pi * 440 * np.arange(24000) / 24000)).astype(np.float32)


def test_wav_header_and_rate():
    data = encode_audio(TONE, "wav")
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    audio, sr = sf.read(io.BytesIO(data))
    assert sr == 24000 and abs(len(audio) - 24000) < 10


def test_mp3_magic():
    data = encode_audio(TONE, "mp3")
    assert data[:3] == b"ID3" or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)


def test_flac_and_opus_magic():
    assert encode_audio(TONE, "flac")[:4] == b"fLaC"
    assert encode_audio(TONE, "opus")[:4] == b"OggS"


def test_pcm_is_raw_int16():
    data = encode_audio(np.array([0.0, 1.0, -1.0], dtype=np.float32), "pcm")
    assert struct.unpack("<3h", data) == (0, 32767, -32767)


def test_handler_success_direct():
    out = handler.handle({"input": "Hello there.", "voice": "af_heart", "response_format": "wav"}, engine=FakeEngine())
    assert "error" not in out
    raw = base64.b64decode(out["audio_base64"])
    assert raw[:4] == b"RIFF" and out["content_type"] == "audio/wav" and out["duration_seconds"] > 0


def test_handler_openai_route():
    out = handler.handle({"openai_route": "/v1/audio/speech",
                          "openai_input": {"model": "tts-1", "input": "Hi.", "voice": "alloy"}}, engine=FakeEngine())
    assert out["voice"] == "af_alloy" and out["format"] == "mp3"


def test_handler_error_is_json():
    out = handler.handle({"input": "Hi", "voice": "nope_voice"}, engine=FakeEngine())
    assert out["error"].startswith("invalid_voice:")
    assert out["error_detail"]["param"] == "voice" and out["status"] == 400


def test_handler_bad_route_and_type():
    assert handler.handle({"openai_route": "/v1/chat/completions"}, engine=FakeEngine())["status"] == 404
    assert "error" in handler.handle("not a dict", engine=FakeEngine())


def test_handler_list_voices():
    out = handler.handle({"action": "list_voices"}, engine=FakeEngine())
    ids = {v["id"] for v in out["data"]}
    assert len(ids) == 54 and "af_heart" in ids


def test_handler_internal_error_is_sanitized():
    class Boom(FakeEngine):
        def synthesize(self, req):
            raise RuntimeError("secret path /root/x")
    out = handler.handle({"input": "Hi."}, engine=Boom())
    assert out["error"] == "internal_error: internal error: RuntimeError" and "secret" not in str(out)
