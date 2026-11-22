import pytest

from tts_core import Settings, TTSError, parse_speech_request, resolve_voice, split_text


def p(**kw):
    return parse_speech_request({"input": "Hello world.", **kw}, Settings())


def test_defaults():
    r = p()
    assert r.voice == "af_heart" and r.lang_code == "a" and r.speed == 1.0 and r.response_format == "mp3"


def test_openai_fields_and_model_alias():
    r = p(model="tts-1", voice="nova", speed=1.5, response_format="WAV")
    assert r.voice == "af_nova" and r.speed == 1.5 and r.response_format == "wav"


def test_text_alias_field():
    r = parse_speech_request({"text": "Hi there."}, Settings())
    assert r.text == "Hi there."


@pytest.mark.parametrize("fmt", ["mp3", "wav", "flac", "opus", "pcm"])
def test_supported_formats(fmt):
    assert p(response_format=fmt).response_format == fmt


def test_aac_is_rejected_clearly():
    with pytest.raises(TTSError) as e:
        p(response_format="aac")
    assert e.value.code == "unsupported_format" and "ffmpeg" in e.value.message


def test_unknown_format():
    with pytest.raises(TTSError) as e:
        p(response_format="ogg_vorbis")
    assert e.value.param == "response_format"


@pytest.mark.parametrize("speed", [0.1, 5, "fast", True])
def test_bad_speed(speed):
    with pytest.raises(TTSError) as e:
        p(speed=speed)
    assert e.value.code == "invalid_speed"


@pytest.mark.parametrize("body", [{}, {"input": ""}, {"input": "   "}, {"input": 5}])
def test_missing_input(body):
    with pytest.raises(TTSError) as e:
        parse_speech_request(body, Settings())
    assert e.value.code == "missing_input"


def test_input_too_long():
    s = Settings()
    s.max_input_chars = 10
    with pytest.raises(TTSError) as e:
        parse_speech_request({"input": "x" * 11}, s)
    assert e.value.code == "input_too_long"


def test_unknown_model():
    with pytest.raises(TTSError) as e:
        p(model="whisper-1")
    assert e.value.code == "model_not_found"


def test_unknown_voice():
    with pytest.raises(TTSError) as e:
        p(voice="af_nobody")
    assert e.value.code == "invalid_voice"


def test_blend_normalized():
    v, terms = resolve_voice("AF_Bella(2) + af_sky", Settings())
    assert v == "af_bella(2)+af_sky(1)" and terms == [("af_bella", 2.0), ("af_sky", 1.0)]


def test_blend_cross_language_rejected():
    with pytest.raises(TTSError):
        resolve_voice("af_bella+ff_siwis", Settings())


def test_language_not_installed():
    with pytest.raises(TTSError) as e:
        parse_speech_request({"input": "こんにちは", "voice": "jf_alpha"}, Settings(), installed_langs={"a", "b"})
    assert e.value.code == "language_not_installed" and "misaki[ja]" in e.value.message


def test_lang_from_voice_prefix():
    assert p(voice="ef_dora").lang_code == "e"
    assert p(voice="zm_yunxi").lang_code == "z"


def test_error_body_shape():
    err = TTSError("bad", param="voice", code="invalid_voice").to_dict()
    assert set(err["error"]) == {"message", "type", "param", "code"}


def test_split_text():
    text = ("This is a sentence. " * 60).strip()
    chunks = split_text(text, max_chars=200)
    assert all(len(c) <= 200 for c in chunks) and " ".join(chunks).replace("  ", " ") == text
    assert split_text("one\n\ntwo") == ["one two"]
    assert all(len(c) <= 100 for c in split_text("word " * 200, max_chars=100))
