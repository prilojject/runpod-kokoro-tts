"""Runpod Serverless (queue) handler for Kokoro-82M text-to-speech.

Accepted job inputs (the "input" object of /run or /runsync):

1. OpenAI-style body directly:
   {"input": "Hello", "voice": "af_heart", "speed": 1.0, "response_format": "mp3"}
2. Runpod OpenAI route wrapper (POST https://api.runpod.ai/v2/<ID>/openai/v1/audio/speech):
   {"openai_route": "/v1/audio/speech", "openai_input": {...same body...}}
3. Utility actions: {"action": "list_voices"} | {"action": "health"} | {"action": "list_models"}

Success output: {"audio_base64": "...", "content_type": "audio/mpeg", "format": "mp3", ...metadata}
Error output: job FAILED with "error" = "<code>: <message>" and output.error_detail = OpenAI-style error.
"""
from __future__ import annotations

import base64
import os
import sys
import time
import traceback

import tts_core
from tts_core import Settings, TTSError, parse_speech_request, synthesize_to_bytes
from voices import voice_catalog

SETTINGS = Settings()
SPEECH_ROUTES = {"/v1/audio/speech", "/audio/speech", "v1/audio/speech"}


def _error(exc: TTSError) -> dict:
    return {"error": f"{exc.code}: {exc.message}", "error_detail": exc.to_dict()["error"], "status": exc.status}


def _models() -> dict:
    return {"object": "list", "data": [{"id": tts_core.MODEL_ID, "object": "model", "owned_by": "hexgrad",
                                        "root": "hexgrad/Kokoro-82M"}]}


def handle(job_input, engine=None) -> dict:
    """Pure function used by the Runpod handler and by tests (engine is injectable)."""
    try:
        if not isinstance(job_input, dict):
            raise TTSError("job input must be a JSON object")
        route = job_input.get("openai_route")
        if route is not None:
            body = job_input.get("openai_input") or {}
            if route in SPEECH_ROUTES:
                job_input = body
            elif route in ("/v1/models", "/models"):
                return _models()
            elif route in ("/v1/audio/voices", "/audio/voices"):
                job_input = {"action": "list_voices"}
            else:
                raise TTSError(f"route '{route}' is not supported; use /v1/audio/speech", code="unsupported_route",
                               status=404)

        action = job_input.get("action")
        if action is not None:
            if action == "list_voices":
                eng = engine or tts_core.get_engine()
                return {"object": "list", "default": SETTINGS.default_voice,
                        "data": voice_catalog(eng.installed_langs)}
            if action == "health":
                eng = engine or tts_core.get_engine()
                return {"status": "ok", "device": eng.device, "languages": sorted(eng.installed_langs)}
            if action == "list_models":
                return _models()
            raise TTSError(f"unknown action '{action}'", param="action", code="unknown_action")

        eng = engine or tts_core.get_engine()
        req = parse_speech_request(job_input, SETTINGS, installed_langs=eng.installed_langs)
        data, meta = synthesize_to_bytes(req, eng, SETTINGS)
        return {"audio_base64": base64.b64encode(data).decode("ascii"), **meta}
    except TTSError as exc:
        return _error(exc)
    except Exception as exc:  # never leak a raw stack trace to the caller
        traceback.print_exc()
        return _error(TTSError(f"internal error: {type(exc).__name__}", code="internal_error", status=500,
                               type_="server_error"))


def handler(job):
    return handle(job.get("input"))


def _preload():
    t0 = time.time()
    eng = tts_core.get_engine()
    if os.environ.get("KOKORO_WARMUP", "1") == "1" and hasattr(eng, "warmup"):
        w = eng.warmup()
        print(f"[kokoro] warmup synth {w:.2f}s", flush=True)
    print(f"[kokoro] ready on {eng.device} in {time.time() - t0:.2f}s; languages={sorted(eng.installed_langs)}",
          flush=True)


if __name__ == "__main__":
    import runpod

    _preload()  # load model + voices before taking jobs, so the first request is not slow
    runpod.serverless.start({"handler": handler})
    sys.exit(0)
