"""Load the repository root as a package (like Hermes does) with Hermes' ABCs importable.

Hermes core is located through ``HERMES_AGENT_SRC`` (a hermes-agent checkout) or an installed
``hermes-agent``; without either, the suite is skipped.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "hermes_plugins.wispr_stt"


def _ensure_hermes() -> None:
    if src := os.environ.get("HERMES_AGENT_SRC"):
        sys.path.insert(0, src)
    if importlib.util.find_spec("agent.transcription_provider") is None:
        pytest.exit(
            "Hermes core not importable: set HERMES_AGENT_SRC to a hermes-agent checkout", returncode=4
        )


def _load_plugin() -> ModuleType:
    if PACKAGE in sys.modules:
        return sys.modules[PACKAGE]
    sys.modules.setdefault("hermes_plugins", ModuleType("hermes_plugins"))
    spec = importlib.util.spec_from_file_location(
        PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return module


_ensure_hermes()
plugin = _load_plugin()


@pytest.fixture
def fake_wispr(tmp_path: Path) -> Path:
    exe = tmp_path / "wispr"
    exe.write_text(f"#!{sys.executable}\n" + (ROOT / "tests" / "fake_wispr.py").read_text())
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


@pytest.fixture
def logged_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "wispr-home"
    home.mkdir()
    (home / "tokens.json").write_text("{}")
    monkeypatch.setenv("WISPR_HOME", str(home))
    return home
