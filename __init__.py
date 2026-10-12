"""Hermes Agent plugin: speech-to-text through Wispr Flow.

Enable with ``stt.provider: wispr`` in ``~/.hermes/config.yaml`` after ``wispr login``.
"""

from __future__ import annotations

from typing import Any

from .provider import PROVIDER_NAME, WisprTranscriptionProvider
from .settings import PluginSettings

__all__ = ["PROVIDER_NAME", "PluginSettings", "WisprTranscriptionProvider", "register"]


def register(ctx: Any) -> None:
    """Hermes entry point (``ctx`` is ``hermes_cli.plugins.PluginContext``)."""
    ctx.register_transcription_provider(
        WisprTranscriptionProvider(lambda: PluginSettings.load(ctx.get_config))
    )
