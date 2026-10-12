# hermes-wispr-stt

[Hermes Agent](https://github.com/NousResearch/hermes-agent) speech-to-text plugin that transcribes your
voice messages with **Wispr Flow**, using your own Wispr account.

It is a thin adapter: all Wispr logic lives in [wispr-client](https://github.com/D4NZ-jpg/wispr-client),
whose `wispr` CLI the plugin calls. The plugin itself has no dependencies beyond pydantic, which ships with Hermes.

> **Unofficial.** Not affiliated with Wispr; uses an undocumented API that may change and whose automated
> use may violate Wispr's terms. Transcriptions count against your Wispr plan. Keep a fallback STT provider.

## Install

On the machine running Hermes:

```bash
# 1. the Wispr client (+ ffmpeg for voice-note formats)
uv tool install git+ssh://git@github.com/D4NZ-jpg/wispr-client.git
sudo apt install ffmpeg            # or brew install ffmpeg
wispr login                        # browser sign-in, once; the session auto-refreshes

# 2. the plugin
hermes plugins install git@github.com:D4NZ-jpg/hermes-wispr-stt.git --enable --yes-deps

# 3. select it
hermes config set stt.provider wispr
hermes config set stt.language en  # optional; omit for auto-detect
hermes config set stt.streaming true  # optional; live voice mode
```

Restart Hermes (`hermes gateway restart` for the gateway).

## Configuration

`~/.hermes/config.yaml`:

```yaml
stt:
  provider: wispr
  language: en          # BCP-47 hint (en, en-GB, es, pt-BR, ...); "" = auto-detect
  prompt: "Nous, Hermes, Teknium"   # optional: comma-separated names/terms become custom vocabulary
  streaming: true       # optional

plugins:
  entries:
    wispr-stt:
      settings:
        formatting: true        # false = raw ASR transcript, skip Wispr's clean-up
        vocabulary: [Danz]      # extra custom words, always sent
        app_name: Hermes Agent  # dictation context sent to Wispr
        timeout_s: 120
        wispr_bin: ""           # path to `wispr` if it is not on PATH / in ~/.local/bin
```

## Behaviour

| | |
|---|---|
| Voice messages (any format ffmpeg reads) | `wispr transcribe --json`; ~1.1 s for an 11 s clip end-to-end |
| Live voice mode (`stt.streaming: true`) | a `wispr stream` process per utterance; final text ~0.4 s after you stop talking. Wispr returns text only at the end, so live partial captions stay empty |
| Availability | provider shows as available once `wispr` is installed and `wispr login` was run (checked offline) |
| Errors | reported through Hermes' error envelope, e.g. `wispr: not logged in (run \`wispr login\`)` |

## Development

```bash
uv sync
HERMES_AGENT_SRC=/path/to/hermes-agent uv run pytest   # fake `wispr` CLI, no network
uv run ruff check . && uv run ruff format --check . && ./scripts/typecheck.sh
hermes plugins validate . && hermes plugins doctor . --ci
```

The repository root is the plugin package (Hermes imports it as `hermes_plugins.wispr_stt`); `tests/_layout.py`
and `scripts/typecheck.sh` handle that for pytest and mypy. `stubs/` types Hermes' `TranscriptionProvider` ABC.
`events.py` mirrors wispr-client's versioned JSON event contract (`v: 1`).
