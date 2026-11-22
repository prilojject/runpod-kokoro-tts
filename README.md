# Kokoro TTS — Runpod Serverless worker (OpenAI-compatible)

Text-to-speech on Runpod Serverless with **[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)**
(82M parameters, Apache-2.0). It accepts the OpenAI `/v1/audio/speech` request body: `input`, `voice`,
`speed`, `response_format`.

- 54 voices in 8 languages are loaded by default (Japanese is optional, see Limitations). OpenAI voice names (`alloy`, `nova`, `onyx`, …) also work.
- Weighted voice blending, for example `af_bella(2)+af_sky(1)`.
- Output formats: `mp3`, `wav`, `flac`, `opus` (Ogg), `pcm` (raw 16-bit LE, 24 kHz mono).
- Errors come back as clear JSON: `{"error": {"message", "type", "param", "code"}}`.
- The weights, all voices and the spaCy model are baked into the image. A cold start does not download anything.

## Quick start (queue endpoint)

Deploy from the Runpod Hub, or build `Dockerfile` yourself. Then:

```bash
curl -s https://api.runpod.ai/v2/$ENDPOINT_ID/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input": {"input": "Hello from Kokoro!", "voice": "af_heart", "speed": 1.0, "response_format": "mp3"}}' \
  | jq -r .output.audio_base64 | base64 -d > speech.mp3
```

Successful output (`output` field of the job):

```json
{
  "audio_base64": "<base64 audio>",
  "content_type": "audio/mpeg",
  "format": "mp3",
  "model": "kokoro",
  "voice": "af_heart",
  "lang_code": "a",
  "speed": 1.0,
  "sample_rate": 24000,
  "duration_seconds": 1.85,
  "bytes": 13152,
  "inference_seconds": 0.12,
  "device": "cuda"
}
```

The job input can also be the Runpod OpenAI wrapper:
`{"openai_route": "/v1/audio/speech", "openai_input": {...OpenAI body...}}`.
Other actions: `{"action": "list_voices"}`, `{"action": "list_models"}`, `{"action": "health"}`.

A Python example is in [`examples/client.py`](examples/client.py).

## Request fields

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `input` (alias `text`) | string | required | Up to `MAX_INPUT_CHARS` (4096). Long text is split into sentences automatically. |
| `voice` | string | `DEFAULT_VOICE` (`af_heart`) | Kokoro id, OpenAI alias, or a blend of up to 4 voices from the same language. |
| `speed` | number | `1.0` | 0.25–4.0. Kokoro sounds most natural between 0.7 and 1.5. |
| `response_format` | string | `DEFAULT_RESPONSE_FORMAT` (`mp3`) | `mp3`, `wav`, `flac`, `opus`, `pcm`. `aac` returns an error. |
| `model` | string | optional | `kokoro`. `tts-1`, `tts-1-hd` and `gpt-4o-mini-tts` are accepted as aliases. |
| `lang_code` | string | from the voice prefix | Override the G2P language (`a`,`b`,`e`,`f`,`h`,`i`,`p`,`z`). |

The `instructions` field is ignored. Kokoro has no prompt-based style control.

## Voices

The first letter of a voice id is its language, and the second letter is its gender (`f`/`m`).
Grades come from the [model's VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

| Language | Prefix | Voices |
| --- | --- | --- |
| American English | `a` | **af_heart** (A), af_bella (A-), af_nicole, af_aoede, af_kore, af_sarah, af_alloy, af_nova, af_sky, af_jessica, af_river, am_fenrir, am_michael, am_puck, am_echo, am_eric, am_liam, am_onyx, am_santa, am_adam |
| British English | `b` | bf_emma, bf_isabella, bf_alice, bf_lily, bm_george, bm_fable, bm_lewis, bm_daniel |
| Spanish | `e` | ef_dora, em_alex, em_santa |
| French | `f` | ff_siwis |
| Hindi | `h` | hf_alpha, hf_beta, hm_omega, hm_psi |
| Italian | `i` | if_sara, im_nicola |
| Brazilian Portuguese | `p` | pf_dora, pm_alex, pm_santa |
| Mandarin Chinese | `z` | zf_xiaobei, zf_xiaoni, zf_xiaoxiao, zf_xiaoyi, zm_yunjian, zm_yunxi, zm_yunxia, zm_yunyang |
| Japanese (not installed by default) | `j` | jf_alpha, jf_gongitsune, jf_nezumi, jf_tebukuro, jm_kumo |

OpenAI aliases: alloy→af_alloy, ash→am_michael, ballad→bm_george, coral→af_nicole, echo→am_echo,
fable→bm_fable, nova→af_nova, onyx→am_onyx, sage→af_sarah, shimmer→af_bella, verse→am_puck.

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `DEFAULT_VOICE` | `af_heart` | Voice used when the request has no `voice`. |
| `DEFAULT_RESPONSE_FORMAT` | `mp3` | Format used when the request has no `response_format`. |
| `MAX_INPUT_CHARS` | `4096` | Longest `input` accepted. |
| `KOKORO_LANGS` | `a,b,e,f,h,i,p,z` | Languages loaded at startup. Fewer languages give a slightly faster start. |
| `KOKORO_WARMUP` | `1` | Runs one tiny synthesis before the worker accepts jobs. |
| `WORKER_MODE` | `queue` | `http` starts the OpenAI HTTP server instead (see below). |
| `API_KEY` | unset | Only in `http` mode: requires `Authorization: Bearer <API_KEY>`. |

No secrets are needed. The model is public and already in the image.

## True OpenAI SDK compatibility (HTTP mode)

A queue endpoint always returns JSON, so the audio arrives base64-encoded. If you want the raw audio bytes
that the OpenAI SDK expects, run the same image with `WORKER_MODE=http`. You can do this on a
**load-balancing** Serverless endpoint or on a Pod (port `80`, or set `PORT`):

```python
from openai import OpenAI
client = OpenAI(base_url="https://<ENDPOINT_ID>.api.runpod.ai/v1", api_key="<RUNPOD_API_KEY>")
with client.audio.speech.with_streaming_response.create(model="kokoro", voice="af_heart",
                                                        input="Hello!", response_format="mp3") as r:
    r.stream_to_file("speech.mp3")
```

HTTP routes: `POST /v1/audio/speech` (binary audio), `GET /v1/audio/voices`, `GET /v1/models`, `GET /ping`.
`/ping` returns 204 while the model loads and 200 once it is ready.

## Recommended GPUs

Kokoro-82M uses about 1–2 GB of VRAM, so a 16 GB card is plenty. The Hub listing uses the pools `AMPERE_16` (RTX A4000,
A4500, RTX 4000/2000 Ada), `AMPERE_24` (L4, A5000, 3090) and `ADA_24` (4090). The image uses CUDA 12.4
(PyTorch 2.6), so the host needs CUDA ≥ 12.4. Blackwell GPUs (RTX 5090 / B200) are not supported by this build.
You can also run it on CPU, but slowly: about 0.5–2× real time.

## Cold start

- The image contains everything. Nothing is downloaded at startup, and `HF_HUB_OFFLINE=1` is set.
- At startup the worker loads the model to the GPU, builds the G2P pipelines and runs a warm-up synthesis before it accepts jobs.
- The image is about 7–8 GB, and most of that is the CUDA PyTorch wheels. After the image is cached on a host, a
  cold start is mostly model load time: a few seconds.

## Local development (no GPU)

```bash
pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt -r requirements-dev.txt
pytest -q                                   # parsing, formats, handler and HTTP tests (fake engine)
KOKORO_FAKE=1 python scripts/dry_run.py     # runs .runpod/tests.json inputs without the model
KOKORO_MODEL_DIR=./models/kokoro python download_assets.py
KOKORO_MODEL_DIR=./models/kokoro python scripts/dry_run.py --real   # real Kokoro on CPU
python handler.py --test_input '{"input": {"input": "Hi", "response_format": "wav"}}'   # Runpod SDK local run
```

## Limitations

- `aac` output is not supported because the image has no ffmpeg. Streaming (`stream_format: "sse"`) and `instructions` are not supported either.
- Japanese is not installed (`misaki[ja]` plus its dictionary would add a lot of size). Japanese voices return a
  clear `language_not_installed` error.
- Kokoro's non-English G2P is thinner than its English G2P, and quality varies by voice (see the grades above).
- Very short inputs (under ~10 tokens) can sound weaker. This is a known trait of the model.
- A queue job returns base64 inside JSON. Keep each request to a few minutes of audio, or split the text.

## License

The worker code is Apache-2.0 (see [LICENSE](LICENSE)). The Kokoro-82M weights and voices are by
[hexgrad](https://huggingface.co/hexgrad/Kokoro-82M) under Apache-2.0. Third-party notices are in [NOTICE](NOTICE).
The image also installs espeak-ng (GPL-3.0), unmodified from PyPI, as a phonemizer fallback.
