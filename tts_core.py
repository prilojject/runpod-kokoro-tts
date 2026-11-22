"""Core logic shared by the queue handler (handler.py) and the HTTP server (server.py).

Everything here except KokoroEngine is pure Python + numpy, so request parsing,
voice resolution and audio encoding can be unit-tested without a GPU or model.
"""
from __future__ import annotations

import io
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from voices import LANGUAGES, OPENAI_VOICE_ALIASES, VOICE_SET

SAMPLE_RATE = 24000
MODEL_ID = "kokoro"
MODEL_ALIASES = {"kokoro", "kokoro-82m", "hexgrad/kokoro-82m", "tts-1", "tts-1-hd", "gpt-4o-mini-tts"}

FORMATS = {
    # name: (content type, soundfile format, soundfile subtype)
    "mp3": ("audio/mpeg", "MP3", None),
    "wav": ("audio/wav", "WAV", "PCM_16"),
    "flac": ("audio/flac", "FLAC", "PCM_16"),
    "opus": ("audio/ogg", "OGG", "OPUS"),
    "pcm": ("audio/pcm", None, None),  # raw 16-bit little-endian mono @ 24 kHz
}
UNSUPPORTED_FORMATS = {"aac": "aac needs an ffmpeg encoder, which this image does not ship; use mp3, opus, flac, wav or pcm"}

_VOICE_TERM = re.compile(r"^\s*([a-z]{2}_[a-z]+)\s*(?:\(\s*([0-9]*\.?[0-9]+)\s*\))?\s*$")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    default_voice: str = field(default_factory=lambda: os.environ.get("DEFAULT_VOICE", "af_heart"))
    default_format: str = field(default_factory=lambda: os.environ.get("DEFAULT_RESPONSE_FORMAT", "mp3"))
    max_input_chars: int = field(default_factory=lambda: _env_int("MAX_INPUT_CHARS", 4096))
    min_speed: float = 0.25
    max_speed: float = 4.0
    mp3_bitrate_quality: float = field(default_factory=lambda: _env_float("MP3_QUALITY", 0.5))


class TTSError(Exception):
    """An error that maps to an OpenAI-style JSON error body."""

    def __init__(self, message: str, *, param: str | None = None, code: str = "invalid_request",
                 status: int = 400, type_: str = "invalid_request_error"):
        super().__init__(message)
        self.message = message
        self.param = param
        self.code = code
        self.status = status
        self.type = type_

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"message": self.message, "type": self.type, "param": self.param, "code": self.code}}


@dataclass
class SpeechRequest:
    text: str
    voice: str                      # normalized voice spec, e.g. "af_bella" or "af_bella(2)+af_sky(1)"
    voice_terms: list[tuple[str, float]]
    lang_code: str
    speed: float
    response_format: str


def resolve_voice(spec: Any, settings: Settings) -> tuple[str, list[tuple[str, float]]]:
    """Parse a voice spec: a Kokoro id, an OpenAI alias, or a weighted blend "a(2)+b(1)"."""
    if spec is None or (isinstance(spec, str) and not spec.strip()):
        spec = settings.default_voice
    if isinstance(spec, dict):  # newer OpenAI SDKs allow {"id": "..."}
        spec = spec.get("id")
    if not isinstance(spec, str):
        raise TTSError("voice must be a string", param="voice", code="invalid_voice")
    raw = spec.strip().lower()
    terms: list[tuple[str, float]] = []
    for part in raw.split("+"):
        part = part.strip()
        alias = OPENAI_VOICE_ALIASES.get(part)
        if alias:
            part = alias
        m = _VOICE_TERM.match(part)
        if not m:
            raise TTSError(f"invalid voice '{spec}'. Use a Kokoro voice id (e.g. af_heart), an OpenAI alias "
                           "(alloy, echo, fable, nova, onyx, shimmer, ...) or a blend like 'af_bella(2)+af_sky(1)'",
                           param="voice", code="invalid_voice")
        name, weight = m.group(1), float(m.group(2)) if m.group(2) else 1.0
        if name not in VOICE_SET:
            raise TTSError(f"unknown voice '{name}'. GET the voice list with {{\"action\": \"list_voices\"}} "
                           "or /v1/audio/voices", param="voice", code="invalid_voice")
        if weight <= 0:
            raise TTSError("voice blend weights must be > 0", param="voice", code="invalid_voice")
        terms.append((name, weight))
    if len(terms) > 4:
        raise TTSError("at most 4 voices can be blended", param="voice", code="invalid_voice")
    langs = {n[0] for n, _ in terms}
    if len(langs) > 1:
        raise TTSError("all voices in a blend must share a language prefix", param="voice", code="invalid_voice")
    if len(terms) == 1:
        normalized = terms[0][0]
    else:
        normalized = "+".join(f"{n}({w:g})" for n, w in terms)
    return normalized, terms


def parse_speech_request(payload: Any, settings: Settings | None = None,
                         installed_langs: set[str] | None = None) -> SpeechRequest:
    """Validate an OpenAI /v1/audio/speech body (plus a few Kokoro extras)."""
    settings = settings or Settings()
    if not isinstance(payload, dict):
        raise TTSError("request body must be a JSON object")
    text = payload.get("input", payload.get("text"))
    if not isinstance(text, str) or not text.strip():
        raise TTSError("'input' is required and must be a non-empty string", param="input", code="missing_input")
    if len(text) > settings.max_input_chars:
        raise TTSError(f"'input' is {len(text)} characters; the limit is {settings.max_input_chars}",
                       param="input", code="input_too_long")

    model = payload.get("model")
    if model is not None and (not isinstance(model, str) or model.strip().lower() not in MODEL_ALIASES):
        raise TTSError(f"unsupported model '{model}'. Use 'kokoro' (OpenAI names tts-1, tts-1-hd and "
                       "gpt-4o-mini-tts are accepted as aliases)", param="model", code="model_not_found")

    voice, terms = resolve_voice(payload.get("voice"), settings)
    lang = payload.get("lang_code") or terms[0][0][0]
    if lang not in LANGUAGES:
        raise TTSError(f"unsupported lang_code '{lang}'", param="lang_code", code="invalid_lang")
    if installed_langs is not None and lang not in installed_langs:
        extra = LANGUAGES[lang][2]
        hint = f" (rebuild the image with {extra})" if extra else ""
        raise TTSError(f"language '{LANGUAGES[lang][1]}' is not installed in this worker{hint}",
                       param="voice", code="language_not_installed")

    speed = payload.get("speed", 1.0)
    if isinstance(speed, bool) or not isinstance(speed, (int, float)):
        raise TTSError("'speed' must be a number", param="speed", code="invalid_speed")
    speed = float(speed)
    if not (settings.min_speed <= speed <= settings.max_speed):
        raise TTSError(f"'speed' must be between {settings.min_speed} and {settings.max_speed}",
                       param="speed", code="invalid_speed")

    fmt = payload.get("response_format") or settings.default_format
    if not isinstance(fmt, str):
        raise TTSError("'response_format' must be a string", param="response_format", code="invalid_format")
    fmt = fmt.strip().lower()
    if fmt in UNSUPPORTED_FORMATS:
        raise TTSError(UNSUPPORTED_FORMATS[fmt], param="response_format", code="unsupported_format")
    if fmt not in FORMATS:
        raise TTSError(f"unsupported response_format '{fmt}'. Supported: {', '.join(FORMATS)}",
                       param="response_format", code="unsupported_format")
    if payload.get("stream_format") not in (None, "audio"):
        raise TTSError("only stream_format='audio' is supported", param="stream_format", code="unsupported_stream")

    return SpeechRequest(text=text, voice=voice, voice_terms=terms, lang_code=lang, speed=speed,
                         response_format=fmt)


def split_text(text: str, max_chars: int = 400) -> list[str]:
    """Split text into sentence groups of at most ~max_chars (Kokoro has a ~510 phoneme window)."""
    text = re.sub(r"[ \t]+", " ", text.strip())
    sentences = re.split(r"(?<=[.!?。！？;:])\s+|\n+", text)
    chunks: list[str] = []
    cur = ""
    for s in (x.strip() for x in sentences):
        if not s:
            continue
        while len(s) > max_chars:  # very long sentence: cut at a space or comma
            cut = max(s.rfind(" ", 0, max_chars), s.rfind(",", 0, max_chars))
            cut = cut if cut > max_chars // 2 else max_chars
            piece, s = s[:cut].strip(), s[cut:].strip()
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(piece)
        if cur and len(cur) + 1 + len(s) > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def encode_audio(audio: np.ndarray, fmt: str, settings: Settings | None = None) -> bytes:
    """Encode mono float32 audio in [-1, 1] at 24 kHz into the requested container."""
    settings = settings or Settings()
    if fmt not in FORMATS:
        raise TTSError(f"unsupported response_format '{fmt}'", param="response_format", code="unsupported_format")
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    audio = np.clip(audio, -1.0, 1.0)
    if fmt == "pcm":
        return (audio * 32767.0).astype("<i2").tobytes()
    import soundfile as sf  # imported lazily so pure-parse tests don't need libsndfile

    _, sf_format, subtype = FORMATS[fmt]
    buf = io.BytesIO()
    kwargs: dict[str, Any] = {}
    if fmt == "mp3":
        kwargs["compression_level"] = settings.mp3_bitrate_quality
    sf.write(buf, audio, SAMPLE_RATE, format=sf_format, subtype=subtype, **kwargs)
    return buf.getvalue()


class FakeEngine:
    """Deterministic stand-in used for dry runs (KOKORO_FAKE=1): a short tone per chunk."""

    installed_langs = set(LANGUAGES)
    device = "fake"

    def synthesize(self, req: SpeechRequest) -> np.ndarray:
        parts = []
        for i, chunk in enumerate(split_text(req.text)):
            dur = min(0.05 * len(chunk) / req.speed, 10.0)
            t = np.arange(int(SAMPLE_RATE * dur)) / SAMPLE_RATE
            parts.append(0.2 * np.sin(2 * np.pi * (220 + 20 * i) * t).astype(np.float32))
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


class KokoroEngine:
    """Loads Kokoro-82M once and keeps one KPipeline per language sharing the same model."""

    def __init__(self, model_dir: str | None = None, langs: str | None = None, device: str | None = None):
        import torch
        from kokoro import KModel

        self._torch = torch
        self.repo_id = "hexgrad/Kokoro-82M"
        self.model_dir = model_dir or os.environ.get("KOKORO_MODEL_DIR", "/models/kokoro")
        if device is None:
            device = os.environ.get("KOKORO_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
        self.device = device
        config = os.path.join(self.model_dir, "config.json")
        weights = os.path.join(self.model_dir, "kokoro-v1_0.pth")
        if os.path.exists(config) and os.path.exists(weights):
            self.model = KModel(repo_id=self.repo_id, config=config, model=weights)
        else:  # fall back to the HF cache / download (slower cold start)
            self.model = KModel(repo_id=self.repo_id)
        self.model = self.model.to(device).eval()
        self._lock = threading.Lock()
        self._pipelines: dict[str, Any] = {}
        self._voice_cache: dict[str, Any] = {}
        wanted = (langs or os.environ.get("KOKORO_LANGS", "a,b,e,f,h,i,p,z")).replace(" ", "").split(",")
        self.installed_langs: set[str] = set()
        for lang in filter(None, wanted):
            try:
                self._pipeline(lang)
                self.installed_langs.add(lang)
            except Exception as exc:  # e.g. misaki[ja] missing
                print(f"[kokoro] language '{lang}' unavailable: {exc}", flush=True)

    def _pipeline(self, lang: str):
        p = self._pipelines.get(lang)
        if p is None:
            from kokoro import KPipeline
            p = KPipeline(lang_code=lang, repo_id=self.repo_id, model=self.model)
            self._pipelines[lang] = p
        return p

    def _voice_tensor(self, req: SpeechRequest):
        key = req.voice
        t = self._voice_cache.get(key)
        if t is not None:
            return t
        torch = self._torch
        packs, weights = [], []
        for name, w in req.voice_terms:
            path = os.path.join(self.model_dir, "voices", f"{name}.pt")
            if os.path.exists(path):
                pack = torch.load(path, weights_only=True)
            else:
                pack = self._pipeline(req.lang_code).load_single_voice(name)
            packs.append(pack.float())
            weights.append(w)
        if len(packs) == 1:
            t = packs[0]
        else:
            wt = torch.tensor(weights, dtype=torch.float32)
            wt = wt / wt.sum()
            t = (torch.stack(packs) * wt.view(-1, *([1] * packs[0].dim()))).sum(dim=0)
        self._voice_cache[key] = t
        return t

    def synthesize(self, req: SpeechRequest) -> np.ndarray:
        pipeline = self._pipeline(req.lang_code)
        voice = self._voice_tensor(req)
        parts = []
        with self._lock, self._torch.inference_mode():
            for result in pipeline(split_text(req.text), voice=voice, speed=req.speed, split_pattern=None):
                audio = result.audio if hasattr(result, "audio") else result[2]
                if audio is not None:
                    parts.append(audio.detach().float().cpu().numpy())
        if not parts:
            raise TTSError("no speech could be generated from 'input' (empty after phonemization)",
                           param="input", code="empty_audio")
        return np.concatenate(parts)

    def warmup(self) -> float:
        t0 = time.time()
        req = SpeechRequest("Warm up.", "af_heart", [("af_heart", 1.0)], "a", 1.0, "wav")
        self.synthesize(req)
        return time.time() - t0


_ENGINE = None
_ENGINE_LOCK = threading.Lock()


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                _ENGINE = FakeEngine() if os.environ.get("KOKORO_FAKE") == "1" else KokoroEngine()
    return _ENGINE


def synthesize_to_bytes(req: SpeechRequest, engine=None, settings: Settings | None = None) -> tuple[bytes, dict]:
    engine = engine or get_engine()
    t0 = time.time()
    audio = engine.synthesize(req)
    data = encode_audio(audio, req.response_format, settings)
    meta = {
        "model": MODEL_ID,
        "voice": req.voice,
        "lang_code": req.lang_code,
        "speed": req.speed,
        "format": req.response_format,
        "content_type": FORMATS[req.response_format][0],
        "sample_rate": SAMPLE_RATE,
        "duration_seconds": round(len(audio) / SAMPLE_RATE, 3),
        "bytes": len(data),
        "inference_seconds": round(time.time() - t0, 3),
        "device": getattr(engine, "device", "unknown"),
    }
    return data, meta
