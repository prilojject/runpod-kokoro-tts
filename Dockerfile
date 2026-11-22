# Kokoro-82M TTS worker for Runpod Serverless.
# Model weights + all voices + spaCy English model are baked into the image, so a cold start
# needs no network: it only loads ~330 MB of weights onto the GPU and runs a short warm-up.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    KOKORO_MODEL_DIR=/models/kokoro \
    HF_HOME=/models/hf \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false

ARG TORCH_VERSION=2.6.0
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu124
ARG KOKORO_REVISION=f3ff3571791e39611d31c381e3a41a3af07b4987

WORKDIR /app

# CUDA 12.4 build of torch (works on T4 / A4000 / L4 / A5000 / 4090; driver >= 550).
RUN pip install "torch==${TORCH_VERSION}" --index-url "${TORCH_INDEX}"

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY download_assets.py .
RUN HF_HUB_OFFLINE=0 KOKORO_REVISION=${KOKORO_REVISION} python download_assets.py

COPY voices.py tts_core.py handler.py server.py start.sh ./

# Build-time smoke test on CPU: loads the baked model and synthesizes one short phrase offline.
RUN KOKORO_DEVICE=cpu KOKORO_LANGS=a python -c "import tts_core as t; e=t.KokoroEngine(); print('build smoke ok', round(e.warmup(),2), 's')"

CMD ["/app/start.sh"]
