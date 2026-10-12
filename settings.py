"""Plugin settings (``plugins.entries.wispr-stt.settings`` in Hermes' config.yaml)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

if TYPE_CHECKING:
    from collections.abc import Callable

_log = logging.getLogger(__name__)


class PluginSettings(BaseModel):
    """Typed view of the ``config_schema`` declared in ``plugin.yaml`` (keep the two in sync)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    wispr_bin: str = ""
    formatting: bool = True
    app_name: str = "Hermes Agent"
    vocabulary: tuple[str, ...] = ()
    timeout_s: float = Field(default=120.0, gt=0, le=3600)

    @field_validator("vocabulary", mode="before")
    @classmethod
    def _split_vocabulary(cls, value: object) -> object:
        """Accept a YAML list or a comma-separated string."""
        if isinstance(value, str):
            return tuple(w.strip() for w in value.split(",") if w.strip())
        return value

    @classmethod
    def load(cls, get_config: Callable[[str, Any], Any]) -> PluginSettings:
        """Read every field through ``ctx.get_config``; invalid values fall back to defaults (logged)."""
        raw = {name: value for name in cls.model_fields if (value := get_config(name, None)) is not None}
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            _log.warning("wispr-stt: invalid plugin settings, using defaults: %s", exc)
            return cls()
