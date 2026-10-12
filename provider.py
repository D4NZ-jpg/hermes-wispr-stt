"""Hermes ``TranscriptionProvider`` backed by the ``wispr`` CLI.

Hermes' contract: ``transcribe``/``push_audio``/``finalize`` must never raise; failures are reported through
the ``{"success", "transcript", "provider", "error"}`` envelope.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import threading
from typing import TYPE_CHECKING, Any, Final

from agent.transcription_provider import TranscriptionProvider, TranscriptionStreamSession

from .events import ErrorEvent, FinalEvent, PartialEvent
from .wispr_cli import WisprCli, find_wispr, parse_event, token_file, vocabulary_terms

if TYPE_CHECKING:
    from collections.abc import Callable

    from .events import StreamEvent
    from .settings import PluginSettings

_log = logging.getLogger(__name__)

PROVIDER_NAME: Final = "wispr"
_FINALIZE_TIMEOUT_S: Final = 30.0
_CLIENT_REPO: Final = "git+https://github.com/D4NZ-jpg/wispr-client.git"
_NOT_INSTALLED: Final = (
    f"wispr CLI not found. Install it with `uv tool install {_CLIENT_REPO}` "
    "or set plugins.entries.wispr-stt.settings.wispr_bin"
)

Envelope = dict[str, Any]


def _ok(text: str) -> Envelope:
    return {"success": True, "transcript": text, "provider": PROVIDER_NAME}


def _fail(error: str) -> Envelope:
    return {"success": False, "transcript": "", "provider": PROVIDER_NAME, "error": f"wispr: {error}"}


def _envelope(event: StreamEvent | None) -> Envelope:
    match event:
        case FinalEvent(result=result):
            return _ok(result.text)
        case ErrorEvent(error=error, kind=kind):
            hint = " (run `wispr login`)" if kind in {"NotLoggedInError", "AuthError"} else ""
            return _fail(f"{error}{hint}")
        case _:
            return _fail("no result from wispr")


class WisprTranscriptionProvider(TranscriptionProvider):
    """Registered as ``stt.provider: wispr``."""

    def __init__(self, settings: Callable[[], PluginSettings]) -> None:
        # A loader, not a snapshot: settings edits apply without restarting Hermes.
        self._settings = settings

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def display_name(self) -> str:
        return "Wispr Flow (unofficial)"

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": self.display_name,
            "badge": "unofficial",
            "tag": "Your Wispr Flow account via the `wispr` CLI; run `wispr login` once",
            "env_vars": [],
        }

    def is_available(self) -> bool:
        """Cheap and offline: CLI present and a session stored."""
        try:
            return find_wispr(self._settings().wispr_bin) is not None and token_file().is_file()
        except Exception:  # noqa: BLE001 (must not raise)
            return False

    def list_models(self) -> list[dict[str, Any]]:
        return [{"id": "wispr-flow", "display": "Wispr Flow"}]

    def transcribe(
        self, file_path: str, *, model: str | None = None, language: str | None = None, **extra: Any
    ) -> Envelope:
        del model  # Wispr exposes a single model
        try:
            settings = self._settings()
            if (exe := find_wispr(settings.wispr_bin)) is None:
                return _fail(_NOT_INSTALLED)
            vocab = vocabulary_terms(extra.get("prompt"), settings.vocabulary)
            return _envelope(WisprCli(exe, settings).transcribe(file_path, language, vocab))
        except Exception as exc:  # noqa: BLE001 (contract: never raise)
            _log.exception("wispr transcription failed")
            return _fail(f"unexpected error: {exc}")

    @property
    def streaming_capable(self) -> bool:
        return True

    def open_stream_session(
        self, *, language: str | None = None, prompt: str | None = None
    ) -> TranscriptionStreamSession:
        return WisprStreamSession(self._settings(), language=language, prompt=prompt)


class WisprStreamSession(TranscriptionStreamSession):
    """One utterance over a ``wispr stream`` subprocess (PCM on stdin, JSON events on stdout).

    Startup failures are deferred to :meth:`finalize`, which reports them in the error envelope.
    """

    def __init__(self, settings: PluginSettings, *, language: str | None, prompt: str | None) -> None:
        self._partial = ""
        self._final: StreamEvent | None = None
        self._error: str | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._reader: threading.Thread | None = None
        self._stderr_tail: list[str] = []

        if (exe := find_wispr(settings.wispr_bin)) is None:
            self._error = _NOT_INSTALLED
            return
        try:
            self._proc = WisprCli(exe, settings).start_stream(
                language, vocabulary_terms(prompt, settings.vocabulary)
            )
        except OSError as exc:
            self._error = f"could not start {exe}: {exc}"
            return
        self._reader = threading.Thread(target=self._read, name="wispr-stt-reader", daemon=True)
        self._reader.start()
        threading.Thread(target=self._drain_stderr, name="wispr-stt-stderr", daemon=True).start()

    def push_audio(self, chunk: bytes) -> None:
        if self._error or self._proc is None or self._proc.stdin is None or not chunk:
            return
        try:
            self._proc.stdin.write(chunk)
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError) as exc:
            self._error = f"wispr stream closed early: {exc}"

    def partial_transcript(self) -> str:
        return self._partial

    def finalize(self) -> Envelope:
        if self._proc is None:
            return _fail(self._error or "stream not started")
        try:
            if self._proc.stdin is not None:
                with contextlib.suppress(OSError, ValueError):
                    self._proc.stdin.close()  # EOF => the CLI commits and waits for the result
            if self._reader is not None:
                self._reader.join(_FINALIZE_TIMEOUT_S)
            if self._reader is not None and self._reader.is_alive():
                self._proc.kill()
                return _fail(f"no result within {_FINALIZE_TIMEOUT_S:.0f}s")
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=5)
            if self._final is None and (self._error or self._stderr_tail):
                return _fail(self._error or self._stderr_tail[-1])
            return _envelope(self._final)
        except Exception as exc:  # noqa: BLE001 (contract: never raise)
            _log.exception("wispr stream finalize failed")
            return _fail(f"unexpected error: {exc}")
        finally:
            if self._proc.poll() is None:
                self._proc.kill()

    def _read(self) -> None:
        if self._proc is None or self._proc.stdout is None:  # pragma: no cover (set before thread start)
            return
        for line in self._proc.stdout:
            match parse_event(line):
                case PartialEvent(text=text):
                    self._partial = text
                case FinalEvent() | ErrorEvent() as event:
                    self._final = event
                case None:
                    _log.debug("wispr-stt: ignoring unparseable line from CLI")

    def _drain_stderr(self) -> None:
        if self._proc is None or self._proc.stderr is None:
            return
        for line in self._proc.stderr:
            if text := line.decode(errors="replace").strip():
                self._stderr_tail = [*self._stderr_tail[-4:], text]
