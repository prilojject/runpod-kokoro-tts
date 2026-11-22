"""Kokoro-82M voice catalog (hexgrad/Kokoro-82M, voices/*.pt).

Snapshot of the 54 voices published in the model repo at revision
f3ff3571791e39611d31c381e3a41a3af07b4987. Grades come from the model's VOICES.md.
"""

# lang prefix -> (Kokoro lang_code, human name, extra needed)
LANGUAGES = {
    "a": ("a", "American English", None),
    "b": ("b", "British English", None),
    "e": ("e", "Spanish", None),
    "f": ("f", "French", None),
    "h": ("h", "Hindi", None),
    "i": ("i", "Italian", None),
    "p": ("p", "Brazilian Portuguese", None),
    "j": ("j", "Japanese", "misaki[ja]"),
    "z": ("z", "Mandarin Chinese", "misaki[zh]"),
}

VOICES = [
    # American English
    "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore",
    "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
    "am_onyx", "am_puck", "am_santa",
    # British English
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    # Japanese
    "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
    # Mandarin Chinese
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    # Spanish
    "ef_dora", "em_alex", "em_santa",
    # French
    "ff_siwis",
    # Hindi
    "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
    # Italian
    "if_sara", "im_nicola",
    # Brazilian Portuguese
    "pf_dora", "pm_alex", "pm_santa",
]
VOICE_SET = frozenset(VOICES)

# OpenAI voice names -> Kokoro voices, so stock OpenAI clients work unchanged.
OPENAI_VOICE_ALIASES = {
    "alloy": "af_alloy",
    "ash": "am_michael",
    "ballad": "bm_george",
    "coral": "af_nicole",
    "echo": "am_echo",
    "fable": "bm_fable",
    "nova": "af_nova",
    "onyx": "am_onyx",
    "sage": "af_sarah",
    "shimmer": "af_bella",
    "verse": "am_puck",
}


def voice_catalog(installed_langs):
    """Return a JSON-friendly list of voices with language and availability."""
    out = []
    for v in VOICES:
        prefix = v[0]
        _, lang_name, _ = LANGUAGES[prefix]
        out.append({
            "id": v,
            "language": lang_name,
            "lang_code": prefix,
            "gender": "female" if v[1] == "f" else "male",
            "available": prefix in installed_langs,
        })
    return out
