# hermes-wispr-stt

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![Hermes plugin API v1](https://img.shields.io/badge/hermes%20plugin-api%20v1-purple)](plugin.yaml)
[![Status: unofficial](https://img.shields.io/badge/status-unofficial-orange)](#hermes-wispr-stt)

A speech-to-text provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent) that transcribes your voice messages with **Wispr Flow**, using your own Wispr account.

[Install](#install) • [Configuration](#configuration) • [How it works](#how-it-works) • [Troubleshooting](#troubleshooting) • [Development](#development)

> [!WARNING]
> This plugin is unofficial and not affiliated with Wispr. It uses an undocumented API that can change at any time, and automated use may violate Wispr's terms. Transcriptions count against your Wispr plan. Keep a fallback STT provider configured.

## Features

- **Voice messages**: transcribes any audio format that ffmpeg can read. An 11 s clip takes about 1.1 s end to end.
- **Live voice mode**: streams microphone audio to Wispr. The final text arrives about 0.4 s after you stop talking.
- **Custom vocabulary**: names and terms from `stt.prompt` and the plugin settings are sent to Wispr as dictionary words.
- **Formatting control**: use Wispr's cleaned-up text or the raw ASR transcript.
- **Hot-reloaded settings**: settings are read on each request, so changes apply without a Hermes restart.
- **Small footprint**: the only runtime dependency is pydantic, which ships with Hermes.

## Requirements

- Hermes Agent with plugin API v1
- [wispr-client](https://github.com/D4NZ-jpg/wispr-client), which provides the `wispr` CLI
- [uv](https://docs.astral.sh/uv/) to install wispr-client
- ffmpeg, for voice-note formats
- A Wispr Flow account

## Install

Run these steps on the machine that runs Hermes.

1. Install the Wispr client and ffmpeg, then sign in once. The session refreshes automatically.

   ```bash
   uv tool install git+https://github.com/D4NZ-jpg/wispr-client.git
   sudo apt install ffmpeg   # or: brew install ffmpeg
   wispr login               # opens a browser sign-in
   ```

2. Install and enable the plugin:

   ```bash
   hermes plugins install https://github.com/D4NZ-jpg/hermes-wispr-stt.git --enable --yes-deps
   ```

3. Select Wispr as the STT provider:

   ```bash
   hermes config set stt.provider wispr
   hermes config set stt.language en     # optional; omit for auto-detect
   hermes config set stt.streaming true  # optional; enables live voice mode
   ```

4. Restart Hermes. For the gateway, run `hermes gateway restart`.

> [!TIP]
> The provider shows as available when the `wispr` executable is found and a Wispr session file exists. This check runs offline.

## Configuration

All settings live in `~/.hermes/config.yaml`.

```yaml
stt:
  provider: wispr
  language: en                     # BCP-47 hint (en, en-GB, es, pt-BR, ...); "" = auto-detect
  prompt: "Nous, Hermes, Teknium"  # optional; terms become custom vocabulary
  streaming: true                  # optional; live voice mode

plugins:
  entries:
    wispr-stt:
      settings:
        formatting: true           # false = raw ASR transcript
        vocabulary: [Danz]         # extra custom words, always sent
        app_name: Hermes Agent     # dictation context sent to Wispr
        timeout_s: 120             # max seconds per file transcription
        wispr_bin: ""              # path to `wispr` if it is not found automatically
```

### Plugin settings

| Setting | Default | Description |
| --- | --- | --- |
| `formatting` | `true` | Use Wispr's formatting and clean-up. Set `false` to get the raw ASR transcript. |
| `vocabulary` | `[]` | Extra words or names to bias recognition. Accepts a YAML list or a comma-separated string. |
| `app_name` | `Hermes Agent` | App name sent to Wispr as dictation context. |
| `timeout_s` | `120` | Maximum seconds for one file transcription (greater than 0, at most 3600). |
| `wispr_bin` | `""` | Path to the `wispr` executable. When empty, the plugin checks `PATH`, then `~/.local/bin/wispr`. |

If a setting is invalid, the plugin logs a warning and uses the defaults for all settings.

### Custom vocabulary

The plugin builds the vocabulary from `plugins.entries.wispr-stt.settings.vocabulary` and `stt.prompt`. It splits `stt.prompt` on commas, semicolons, and newlines, and keeps only fragments of five words or fewer. Full sentences are dropped because they are not useful as dictionary entries. Duplicates are removed, and at most 100 terms are sent.

## How it works

The plugin is a thin adapter. All Wispr logic lives in [wispr-client](https://github.com/D4NZ-jpg/wispr-client), and the plugin calls its `wispr` CLI in a subprocess. It does not import wispr-client, which stays in its own isolated tool environment.

```text
Hermes ──► WisprTranscriptionProvider ──► wispr transcribe --json <file>   (voice messages)
                                     └──► wispr stream                     (live voice mode)
                                            PCM audio on stdin, JSON events on stdout
```

- **Voice messages** run `wispr transcribe --json` and read the last JSON event from its output.
- **Live voice mode** starts one `wispr stream` process per utterance. When the utterance ends, the plugin closes stdin and waits up to 30 s for the final result. Wispr returns text only at the end, so live partial captions stay empty.
- **Errors** are returned through Hermes' result envelope and never raised. Messages start with `wispr:`, for example ``wispr: not logged in (run `wispr login`)``.

`events.py` mirrors the CLI's versioned JSON event contract (`v: 1`). Unknown fields are ignored, so additive CLI changes do not break the plugin.

## Troubleshooting

| Error or symptom | Fix |
| --- | --- |
| `wispr CLI not found` | Install wispr-client with `uv tool install`, or set `wispr_bin` to the full path of the executable. |
| ``not logged in (run `wispr login`)`` | Run `wispr login` as the same user that runs Hermes. |
| Provider not listed as available | Check that `wispr` is installed and that the session file exists. The plugin reads `$WISPR_HOME/tokens.json` if `WISPR_HOME` is set. Otherwise it reads `$XDG_CONFIG_HOME/wispr-client/tokens.json`, which defaults to `~/.config/wispr-client/tokens.json`. |
| `wispr timed out after …s` | Increase `timeout_s` for long recordings. |
| Voice note format fails | Install ffmpeg on the Hermes machine. |

## Development

```bash
uv sync
HERMES_AGENT_SRC=/path/to/hermes-agent uv run pytest
uv run ruff check . && uv run ruff format --check . && ./scripts/typecheck.sh
hermes plugins validate . && hermes plugins doctor . --ci
```

The tests use a fake `wispr` CLI (`tests/fake_wispr.py`) and make no network calls. They need Hermes core to be importable: set `HERMES_AGENT_SRC` to a hermes-agent checkout, or install `hermes-agent` in the environment.

> [!NOTE]
> The repository root is the plugin package. Hermes imports it as `hermes_plugins.wispr_stt`. `tests/_layout.py` and `scripts/typecheck.sh` set up that layout for pytest and mypy. `stubs/` provides types for Hermes' `TranscriptionProvider` base classes so that `mypy --strict` runs offline.

| File | Purpose |
| --- | --- |
| `__init__.py` | Hermes entry point (`register`) |
| `provider.py` | `TranscriptionProvider` and the streaming session |
| `wispr_cli.py` | Finds and runs the `wispr` CLI, builds vocabulary terms |
| `settings.py` | Typed plugin settings; keep in sync with `config_schema` in `plugin.yaml` |
| `events.py` | Copy of the CLI's JSON event schema |
