"""Build-time download of Kokoro-82M weights + all voices into the image (no network at cold start)."""
import os
import sys

from huggingface_hub import snapshot_download

REPO = "hexgrad/Kokoro-82M"
REVISION = os.environ.get("KOKORO_REVISION", "f3ff3571791e39611d31c381e3a41a3af07b4987")
TARGET = os.environ.get("KOKORO_MODEL_DIR", "/models/kokoro")

path = snapshot_download(
    repo_id=REPO,
    revision=REVISION,
    local_dir=TARGET,
    allow_patterns=["config.json", "kokoro-v1_0.pth", "voices/*.pt", "README.md", "VOICES.md"],
)
voices = sorted(f for f in os.listdir(os.path.join(path, "voices")) if f.endswith(".pt"))
size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(path) for f in fs)
print(f"downloaded {REPO}@{REVISION[:8]} to {path}: {len(voices)} voices, {size / 1e6:.0f} MB")
if len(voices) < 50 or not os.path.exists(os.path.join(path, "kokoro-v1_0.pth")):
    sys.exit("model download incomplete")
