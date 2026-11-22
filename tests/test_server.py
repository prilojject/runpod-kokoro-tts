import pytest
from fastapi.testclient import TestClient

import server


@pytest.fixture(scope="module")
def client():
    with TestClient(server.app) as c:
        server._ready.wait(10)
        yield c


def test_ping(client):
    assert client.get("/ping").status_code == 200


def test_speech_binary(client):
    r = client.post("/v1/audio/speech", json={"model": "tts-1", "input": "Hello.", "voice": "nova",
                                             "response_format": "wav"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content[:4] == b"RIFF"


def test_speech_error_json(client):
    r = client.post("/v1/audio/speech", json={"input": "Hello.", "response_format": "aac"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unsupported_format"


def test_bad_json(client):
    r = client.post("/v1/audio/speech", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_json"


def test_voices_and_models(client):
    assert len(client.get("/v1/audio/voices").json()["data"]) == 54
    assert client.get("/v1/models").json()["data"][0]["id"] == "kokoro"
