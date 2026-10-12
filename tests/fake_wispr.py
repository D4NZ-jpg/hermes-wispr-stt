#!/usr/bin/env python3
"""Stand-in for the `wispr` CLI. Behaviour is selected with FAKE_WISPR_MODE:
ok (default) | notloggedin | crash | garbage. Echoes its arguments into the transcript so tests can assert
what the plugin passed."""

import json
import os
import sys


def event(obj: dict[str, object]) -> None:
    sys.stdout.write(json.dumps({"v": 1, **obj}) + "\n")
    sys.stdout.flush()


def main() -> int:
    mode = os.environ.get("FAKE_WISPR_MODE", "ok")
    cmd, args = sys.argv[1], sys.argv[2:]
    if mode == "crash":
        sys.stderr.write("Traceback...\nRuntimeError: boom\n")
        return 1
    if mode == "garbage":
        sys.stdout.write("not json\n")
        return 1
    if mode == "notloggedin":
        event({"type": "error", "error": "not logged in", "kind": "NotLoggedInError"})
        return 3

    received = 0
    if cmd == "stream":
        while chunk := os.read(0, 4096):
            received += len(chunk)
            if received >= 3200:
                event({"type": "partial", "text": "partial words"})
    text = f"heard {received} bytes; args={' '.join(args)}"
    event(
        {
            "type": "final",
            "result": {
                "text": text,
                "status": "formatted",
                "languages": ["en"],
                "request_id": "r",
                "future_field": 1,
            },
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
