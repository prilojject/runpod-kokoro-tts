"""Optional HTTP server for Runpod load-balancing endpoints or Pods (WORKER_MODE=http).

Exposes a byte-for-byte OpenAI-compatible API:
  POST /v1/audio/speech  -> raw audio bytes (Content-Type per response_format)
  GET  /v1/audio/voices  -> voice catalog
  GET  /v1/models        -> model list
  GET  /ping             -> 200 when ready, 204 while loading (Runpod LB health contract)
"""
from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

import tts_core
from tts_core import FORMATS, Settings, TTSError, parse_speech_request, synthesize_to_bytes
from voices import voice_catalog

SETTINGS = Settings()
API_KEY = os.environ.get("API_KEY") or None  # optional bearer token for Pod deployments
_ready = threading.Event()


def _load():
    eng = tts_core.get_engine()
    if os.environ.get("KOKORO_WARMUP", "1") == "1" and hasattr(eng, "warmup"):
        eng.warmup()
    _ready.set()


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_load, daemon=True).start()
    yield


app = FastAPI(title="Kokoro TTS (OpenAI-compatible)", lifespan=lifespan)


def _err(exc: TTSError) -> JSONResponse:
    return JSONResponse(exc.to_dict(), status_code=exc.status)


def _auth(request: Request):
    if API_KEY and request.headers.get("authorization", "") != f"Bearer {API_KEY}":
        raise TTSError("invalid or missing API key", code="invalid_api_key", status=401,
                       type_="authentication_error")


@app.get("/ping")
def ping():
    return Response(status_code=200 if _ready.is_set() else 204)


@app.get("/v1/models")
def models(request: Request):
    try:
        _auth(request)
    except TTSError as e:
        return _err(e)
    return {"object": "list", "data": [{"id": tts_core.MODEL_ID, "object": "model", "owned_by": "hexgrad"}]}


@app.get("/v1/audio/voices")
def voices(request: Request):
    try:
        _auth(request)
        if not _ready.is_set():
            raise TTSError("model is still loading", code="loading", status=503, type_="server_error")
        eng = tts_core.get_engine()
        return {"object": "list", "default": SETTINGS.default_voice, "data": voice_catalog(eng.installed_langs)}
    except TTSError as e:
        return _err(e)


@app.post("/v1/audio/speech")
async def speech(request: Request):
    try:
        _auth(request)
        try:
            body = await request.json()
        except Exception:
            raise TTSError("request body must be valid JSON", code="invalid_json")
        if not _ready.is_set():
            raise TTSError("model is still loading, retry shortly", code="loading", status=503, type_="server_error")
        eng = tts_core.get_engine()
        req = parse_speech_request(body, SETTINGS, installed_langs=eng.installed_langs)
        data, meta = await run_in_threadpool(synthesize_to_bytes, req, eng, SETTINGS)
        headers = {"X-Audio-Duration": str(meta["duration_seconds"]), "X-Voice": meta["voice"],
                   "X-Sample-Rate": str(meta["sample_rate"])}
        return Response(content=data, media_type=FORMATS[req.response_format][0], headers=headers)
    except TTSError as e:
        return _err(e)
    except Exception as e:
        return _err(TTSError(f"internal error: {type(e).__name__}", code="internal_error", status=500,
                             type_="server_error"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "80")))
