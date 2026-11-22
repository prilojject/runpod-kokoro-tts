"""Call a deployed endpoint. Requires RUNPOD_API_KEY and ENDPOINT_ID in the environment.

  python examples/client.py "Hello world" af_heart mp3
"""
import base64
import os
import sys

import requests

text = sys.argv[1] if len(sys.argv) > 1 else "Hello from Kokoro on Runpod."
voice = sys.argv[2] if len(sys.argv) > 2 else "af_heart"
fmt = sys.argv[3] if len(sys.argv) > 3 else "mp3"

url = f"https://api.runpod.ai/v2/{os.environ['ENDPOINT_ID']}/runsync"
r = requests.post(url, headers={"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"},
                  json={"input": {"input": text, "voice": voice, "response_format": fmt}}, timeout=120)
r.raise_for_status()
job = r.json()
if job.get("status") != "COMPLETED":
    sys.exit(f"job {job.get('status')}: {job.get('error')}")
out = job["output"]
with open(f"speech.{out['format']}", "wb") as f:
    f.write(base64.b64decode(out["audio_base64"]))
print(f"saved speech.{out['format']} ({out['duration_seconds']} s, {out['inference_seconds']} s inference)")
