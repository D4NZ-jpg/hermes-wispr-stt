"""The ``wispr`` CLI's JSON-lines event contract (schema v1), mirrored from wispr-client's ``models.py``.

Kept as a copy on purpose: the plugin talks to the CLI over a process boundary and must not import
wispr-client (which lives in its own isolated tool environment). ``tests/test_contract.py`` checks the
two definitions agree when wispr-client is importable.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _Event(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)  # tolerate additive CLI changes
    v: Literal[1]


class TranscriptionResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    text: str
    raw_text: str = ""
    languages: tuple[str, ...] = ()
    status: str = "unspecified"
    confidence: float | None = None
    audio_seconds: float | None = None
    origin: str | None = None
    request_id: str = ""


class PartialEvent(_Event):
    type: Literal["partial"]
    text: str


class FinalEvent(_Event):
    type: Literal["final"]
    result: TranscriptionResult


class ErrorEvent(_Event):
    type: Literal["error"]
    error: str
    kind: str = "WisprError"


StreamEvent = Annotated[PartialEvent | FinalEvent | ErrorEvent, Field(discriminator="type")]
EVENT_ADAPTER: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)
