#!/usr/bin/env bash
# mypy --strict for a repo-root package: mount the repo as `hermes_plugins.wispr_stt` (the namespace
# Hermes imports it under) in a temp dir, then check it plus the tests.
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
tmp="$(mktemp -d)"
trap 'rm -r -- "$tmp"' EXIT
mkdir "$tmp/hermes_plugins"
touch "$tmp/hermes_plugins/__init__.py"
ln -s "$root" "$tmp/hermes_plugins/wispr_stt"
MYPYPATH="$root/stubs:$tmp" uv run mypy -p hermes_plugins.wispr_stt
MYPYPATH="$root/stubs:$tmp" uv run mypy tests
