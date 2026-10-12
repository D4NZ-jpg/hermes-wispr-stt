"""Pytest plugin: collect the repo root as a plain directory.

The repository root *is* the Hermes plugin package (``__init__.py`` with relative imports). Pytest would
otherwise treat it as a test package and import ``__init__.py`` outside its parent package.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def pytest_collect_directory(path: Path, parent: pytest.Collector) -> pytest.Collector | None:
    if path == ROOT:
        return pytest.Dir.from_parent(parent, path=path)
    return None
