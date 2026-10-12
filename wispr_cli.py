"""Locating and invoking the ``wispr`` CLI (from wispr-client)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pydantic import ValidationError

from .events import EVENT_ADAPTER, ErrorEvent, StreamEvent

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .settings import PluginSettings

_PROMPT_SPLIT: Final = re.compile(r"[,;\n]+")
_MAX_TERM_WORDS: Final = 5
_MAX_TERMS: Final = 100


def find_wispr(configured: str = "") -> Path | None:
    """Configured path, else ``wispr`` on PATH, else uv's default tool bin dir."""
    candidates: list[str | None] = [configured or None, shutil.which("wispr")]
    candidates.append(str(Path.home() / ".local" / "bin" / ("wispr.exe" if os.name == "nt" else "wispr")))
    for candidate in candidates:
        if candidate and (path := Path(candidate).expanduser()).is_file() and os.access(path, os.X_OK):
            return path
    return None


def token_file() -> Path:
    """Where wispr-client keeps its session (mirrors ``WisprSettings.home``)."""
    if home := os.environ.get("WISPR_HOME"):
        return Path(home) / "tokens.json"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "wispr-client" / "tokens.json"


def vocabulary_terms(prompt: str | None, extra: Iterable[str] = ()) -> list[str]:
    """Turn Hermes' free-text ``prompt`` hint plus configured words into short dictionary terms.

    Only comma/semicolon/newline-separated fragments of up to five words are kept: whole sentences are
    not useful as dictionary entries.
    """
    terms = [t.strip() for t in _PROMPT_SPLIT.split(prompt or "")]
    seen: dict[str, None] = {}
    for term in (*extra, *terms):
        if term and len(term.split()) <= _MAX_TERM_WORDS:
            seen.setdefault(term, None)
    return list(seen)[:_MAX_TERMS]


class WisprCli:
    def __init__(self, exe: Path, settings: PluginSettings) -> None:
        self.exe = exe
        self.settings = settings

    def _args(self, command: str, language: str | None, vocabulary: Sequence[str]) -> list[str]:
        args = [str(self.exe), command, "--app-name", self.settings.app_name]
        if language:
            args += ["--language", language]
        if not self.settings.formatting:
            args.append("--raw")
        for term in vocabulary:
            args += ["--vocab", term.replace(",", " ")]
        return args

    def transcribe(self, file_path: str, language: str | None, vocabulary: Sequence[str]) -> StreamEvent:
        """Run ``wispr transcribe --json``; always returns an event (never raises for CLI failures)."""
        args = [*self._args("transcribe", language, vocabulary), "--json", "--", file_path]
        try:
            proc = subprocess.run(args, capture_output=True, timeout=self.settings.timeout_s, check=False)
        except subprocess.TimeoutExpired:
            return ErrorEvent(
                v=1,
                type="error",
                error=f"wispr timed out after {self.settings.timeout_s:.0f}s",
                kind="Timeout",
            )
        except OSError as exc:
            return ErrorEvent(v=1, type="error", error=f"could not run {self.exe}: {exc}", kind="OSError")
        return parse_last_event(proc.stdout, proc.stderr, proc.returncode)

    def start_stream(self, language: str | None, vocabulary: Sequence[str]) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            self._args("stream", language, vocabulary),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


def parse_event(line: bytes | str) -> StreamEvent | None:
    try:
        return EVENT_ADAPTER.validate_json(line)
    except ValidationError:
        return None


def parse_last_event(stdout: bytes, stderr: bytes, returncode: int) -> StreamEvent:
    """The final JSON event on stdout, or an ``ErrorEvent`` built from stderr."""
    for line in reversed(stdout.splitlines()):
        if line.strip() and (event := parse_event(line)) is not None:
            return event
    detail = stderr.decode(errors="replace").strip().splitlines()
    message = detail[-1] if detail else f"wispr exited with code {returncode} and no output"
    return ErrorEvent(v=1, type="error", error=message, kind="CliError")
