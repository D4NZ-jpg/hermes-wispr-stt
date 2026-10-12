from __future__ import annotations

from pathlib import Path
from typing import Any

import hermes_plugins.wispr_stt as plugin  # loaded by conftest under Hermes' namespace
import pytest
from agent.transcription_provider import TranscriptionProvider
from hermes_plugins.wispr_stt import wispr_cli as cli_mod
from hermes_plugins.wispr_stt.settings import PluginSettings


def make_provider(**settings: Any) -> plugin.WisprTranscriptionProvider:
    return plugin.WisprTranscriptionProvider(lambda: PluginSettings(**settings))


@pytest.fixture
def audio(tmp_path: Path) -> str:
    path = tmp_path / "note.ogg"
    path.write_bytes(b"OggS fake")
    return str(path)


# --------------------------------------------------------------------------- registration & metadata


def test_register_uses_ctx_settings() -> None:
    registered: list[TranscriptionProvider] = []

    class Ctx:
        def register_transcription_provider(self, p: TranscriptionProvider) -> None:
            registered.append(p)

        def get_config(self, key: str, default: Any = None) -> Any:
            return {"app_name": "Telegram", "vocabulary": "Nous, Hermes"}.get(key, default)

    plugin.register(Ctx())
    (provider,) = registered
    assert isinstance(provider, TranscriptionProvider)
    assert isinstance(provider, plugin.WisprTranscriptionProvider)
    assert provider.name == "wispr"
    assert provider.streaming_capable
    assert provider.default_model() == "wispr-flow"
    loaded = provider._settings()
    assert loaded.app_name == "Telegram"
    assert loaded.vocabulary == ("Nous", "Hermes")


def test_invalid_settings_fall_back_to_defaults() -> None:
    loaded = PluginSettings.load({"timeout_s": -5}.get)
    assert loaded == PluginSettings()


def test_is_available(fake_wispr: Path, logged_in: Path) -> None:
    assert make_provider(wispr_bin=str(fake_wispr)).is_available()
    (logged_in / "tokens.json").unlink()
    assert not make_provider(wispr_bin=str(fake_wispr)).is_available()


@pytest.mark.parametrize(
    ("prompt", "extra", "expected"),
    [
        ("Hermes, Nous Research; Teknium\nWispr", (), ["Hermes", "Nous Research", "Teknium", "Wispr"]),
        ("This is a long sentence that is not a vocabulary term at all", (), []),
        (None, ("Danz",), ["Danz"]),
        ("Danz, Hermes", ("Danz",), ["Danz", "Hermes"]),
    ],
)
def test_vocabulary_terms(prompt: str | None, extra: tuple[str, ...], expected: list[str]) -> None:
    assert cli_mod.vocabulary_terms(prompt, extra) == expected


# --------------------------------------------------------------------------- CLI environment

_INHERITED_PYTHON_ENV = {
    "PYTHONPATH": "/hermes/site-packages",
    "PYTHONHOME": "/hermes",
    "VIRTUAL_ENV": "/hermes/.venv",
    "VIRTUAL_ENV_PROMPT": "hermes",
    "__PYVENV_LAUNCHER__": "/hermes/.venv/bin/python",
}


@pytest.fixture
def python_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_WISPR_MODE", "env")
    monkeypatch.setenv("WISPR_HOME", "/kept")
    for key, value in _INHERITED_PYTHON_ENV.items():
        monkeypatch.setenv(key, value)


def _env_keys(transcript: str) -> set[str]:
    return set(transcript.split("args=", 1)[1].split())


@pytest.mark.usefixtures("python_env")
def test_transcribe_strips_python_env(fake_wispr: Path, audio: str) -> None:
    result = make_provider(wispr_bin=str(fake_wispr)).transcribe(audio)
    assert result["success"] is True
    keys = _env_keys(result["transcript"])
    assert not keys & _INHERITED_PYTHON_ENV.keys()
    assert "WISPR_HOME" in keys


@pytest.mark.usefixtures("python_env")
def test_stream_strips_python_env(fake_wispr: Path) -> None:
    session = make_provider(wispr_bin=str(fake_wispr)).open_stream_session()
    session.push_audio(b"\x00" * 640)
    result = session.finalize()
    assert result["success"] is True
    keys = _env_keys(result["transcript"])
    assert not keys & _INHERITED_PYTHON_ENV.keys()
    assert "WISPR_HOME" in keys


# --------------------------------------------------------------------------- file transcription


def test_transcribe_success_passes_options(fake_wispr: Path, audio: str) -> None:
    provider = make_provider(
        wispr_bin=str(fake_wispr), formatting=False, app_name="Hermes", vocabulary=("Danz",)
    )
    result = provider.transcribe(audio, language="en-GB", prompt="Nous Research")
    assert result["success"] is True
    assert result["provider"] == "wispr"
    transcript = result["transcript"]
    assert "--language en-GB" in transcript
    assert "--raw" in transcript
    assert "--vocab Danz --vocab Nous Research" in transcript
    assert "--json --" in transcript
    assert transcript.endswith(audio)


def test_transcribe_not_logged_in_hint(fake_wispr: Path, audio: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_WISPR_MODE", "notloggedin")
    result = make_provider(wispr_bin=str(fake_wispr)).transcribe(audio)
    assert result == {
        "success": False,
        "transcript": "",
        "provider": "wispr",
        "error": "wispr: not logged in (run `wispr login`)",
    }


@pytest.mark.parametrize(
    ("mode", "error"), [("crash", "RuntimeError: boom"), ("garbage", "exited with code 1")]
)
def test_transcribe_cli_failures(
    fake_wispr: Path, audio: str, monkeypatch: pytest.MonkeyPatch, mode: str, error: str
) -> None:
    monkeypatch.setenv("FAKE_WISPR_MODE", mode)
    result = make_provider(wispr_bin=str(fake_wispr)).transcribe(audio)
    assert result["success"] is False
    assert error in result["error"]


def test_transcribe_missing_cli(audio: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    result = make_provider(wispr_bin="/nonexistent/wispr").transcribe(audio)
    assert result["success"] is False
    assert "uv tool install" in result["error"]


# --------------------------------------------------------------------------- streaming


def test_stream_session(fake_wispr: Path) -> None:
    session = make_provider(wispr_bin=str(fake_wispr)).open_stream_session(language="en")
    for _ in range(10):
        session.push_audio(b"\x00" * 640)
    result = session.finalize()
    assert result["success"] is True
    assert result["transcript"].startswith("heard 6400 bytes;")
    assert "--language en" in result["transcript"]
    assert session.partial_transcript() == "partial words"


def test_stream_session_crash_reports_error(fake_wispr: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_WISPR_MODE", "crash")
    session = make_provider(wispr_bin=str(fake_wispr)).open_stream_session()
    for _ in range(50):
        session.push_audio(b"\x00" * 640)  # must not raise even though the process died
    result = session.finalize()
    assert result["success"] is False
    assert "boom" in result["error"] or "closed early" in result["error"]


def test_stream_session_missing_cli_defers_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    session = make_provider(wispr_bin="/nope").open_stream_session()
    session.push_audio(b"\x00\x00")
    assert session.finalize()["success"] is False
