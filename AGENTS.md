# AGENTS.md

Instructions for coding agents working in `prilojject/runpod-kokoro-tts`.

## What this repo is

A Runpod Serverless worker for Kokoro-82M text-to-speech with an OpenAI-compatible `/v1/audio/speech` body. Default mode is a queue worker (audio as `output.audio_base64`). `WORKER_MODE=http` starts a FastAPI server for the official OpenAI SDK (`POST /v1/audio/speech` returns raw audio bytes).

## Layout

- `handler.py` — Runpod Serverless (queue) entry point
- `server.py` — HTTP mode (OpenAI-compatible routes)
- `tts_core.py` — synthesis, formats, sentence splitting
- `voices.py` — voice ids, OpenAI aliases, blends
- `download_assets.py` — used at image build time to bake weights into the image
- `.runpod/hub.json`, `.runpod/tests.json` — Hub metadata and official tests
- `examples/client.py` — queue client example
- `scripts/dry_run.py` — local runs; `KOKORO_FAKE=1` avoids the real model
- `tests/` — unit tests with a fake engine (no GPU required)
- `NOTICE` — third-party licenses (Kokoro-82M, espeak-ng, …)

## Local checks (no GPU, no paid cloud)

```bash
pip install -r requirements-dev.txt
# For full requirements, install CPU torch first as in the README
pytest -q
KOKORO_FAKE=1 python scripts/dry_run.py
```

Do not add tests that require a real GPU or download weights in CI. Use `KOKORO_FAKE=1` or the existing fake engine fixtures.

## Paid GPU jobs

- Do not start a Runpod pod or Serverless worker unless a human (or an already approved test plan) explicitly asked for a GPU test.
- Prefer a 16 GB pool (`AMPERE_16`, A4000-class). This model needs about 1–2 GB VRAM.
- Delete the endpoint or pod as soon as the test finishes.
- This image is CUDA 12.4 / PyTorch 2.6. Do not schedule it on Blackwell (RTX 5090 / B200); those GPUs are not supported.

## Behaviour to preserve

- Weights and default voices stay baked into the image. Do not make startup download from Hugging Face (the image sets `HF_HUB_OFFLINE=1`).
- Keep OpenAI field names: `input`, `voice`, `speed`, `response_format`. `tts-1`, `tts-1-hd`, and `gpt-4o-mini-tts` are model aliases. `instructions` is ignored.
- Errors are JSON: `{"error": {"message", "type", "param", "code"}}`.
- Japanese is not installed by default; Japanese voices must keep returning `language_not_installed`.
- `aac` and `stream_format: "sse"` stay unsupported unless ffmpeg/streaming is deliberately added and documented.
- Queue mode returns base64 in JSON; HTTP mode returns binary audio. Do not break either path.

## Secrets

- No Hugging Face token is required at runtime. In HTTP mode, optional `API_KEY` is an env var, never a value committed to git.
- Do not print `.env`, secret files, or API keys.

## Conventions

- After changing `.runpod/hub.json` or `.runpod/tests.json`, run `pytest`.
- Public docs are English. Keep the first paragraph of `README.md` explicit about what the worker is and who it is for. Update `llms.txt` if you add important docs.
- If you add features that another Kokoro listing already has (for example word-level timestamps), document the difference honestly in the README comparison section.

## Deploy reminders

- Hub listing URL: `https://console.runpod.io/hub/prilojject/runpod-kokoro-tts` (live after review).
- A GitHub release is required before a Hub submission.
- Prefer documenting both queue and HTTP usage; many agents will look for the OpenAI SDK snippet.
