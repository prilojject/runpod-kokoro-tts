"""Local dry run without a GPU.

  KOKORO_FAKE=1 python scripts/dry_run.py            # no model: validates handler + encoding with a tone
  KOKORO_MODEL_DIR=./models/kokoro python scripts/dry_run.py --real   # real Kokoro on CPU
Writes sample files to ./out/ (git-ignored).
"""
import base64
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if "--real" not in sys.argv:
    os.environ["KOKORO_FAKE"] = "1"
os.environ.setdefault("KOKORO_DEVICE", "cpu")

import handler  # noqa: E402
import tts_core  # noqa: E402

with open(os.path.join(ROOT, ".runpod", "tests.json")) as f:
    cases = json.load(f)["tests"]

t0 = time.time()
eng = tts_core.get_engine()
print(f"engine={type(eng).__name__} device={eng.device} langs={sorted(eng.installed_langs)} load={time.time()-t0:.1f}s")
os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
failed = 0
for case in cases + [{"name": "expected_error_bad_voice", "input": {"input": "x", "voice": "zz_none"}, "expect_error": True}]:
    t = time.time()
    out = handler.handle(case["input"])
    ok = ("error" in out) == bool(case.get("expect_error"))
    failed += not ok
    summary = {k: v for k, v in out.items() if k != "audio_base64" and k != "data"}
    if "data" in out:
        summary["voices"] = len(out["data"])
    if "audio_base64" in out:
        path = os.path.join(ROOT, "out", f"{case['name']}.{out['format']}")
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(out["audio_base64"]))
        summary["file"] = os.path.relpath(path, ROOT)
    print(f"{'PASS' if ok else 'FAIL'} {case['name']} {time.time()-t:.2f}s {json.dumps(summary)}")
sys.exit(1 if failed else 0)
