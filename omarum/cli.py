"""`omarum daemon | toggle | start | stop | status`"""

from __future__ import annotations

import argparse
import asyncio
import sys

from omarum.ipc import SOCKET_PATH, DaemonNotRunning, send_command


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="omarum", description="Talk to Rum.")
    parser.add_argument("command", choices=["daemon", "toggle", "start", "stop", "status", "reload", "settings", "ptt_down", "ptt_up", "shortcuts", "tap", "watch"])
    args = parser.parse_args(argv)

    if args.command == "settings":
        import os
        from pathlib import Path

        launcher = Path(__file__).resolve().parent.parent / "bin" / "omarum-settings"
        os.execv(str(launcher), [str(launcher)])

    if args.command == "watch":  # for the bar button: one JSON line per state change
        import json

        from omarum.ipc import watch

        last = [None]

        def show(msg: dict) -> None:
            out = {k: v for k, v in msg.items() if k != "type"}
            if out != last[0]:
                last[0] = out
                print(json.dumps(out), flush=True)

        try:
            watch(SOCKET_PATH, show)
        except (KeyboardInterrupt, BrokenPipeError):
            pass
        return

    if args.command == "shortcuts":
        import shutil

        from omarum.config import load_config
        from omarum.shortcuts import apply, conflicts, current_binds

        cfg = load_config()
        apply(cfg, shutil.which("omarum") or sys.argv[0])
        for name in ("talk_shortcut", "settings_shortcut"):
            for c in conflicts(getattr(cfg, name), current_binds()):
                print(f"warning: {getattr(cfg, name)} is also used by: {c}", file=sys.stderr)
        print(f"talk: {cfg.talk_shortcut or 'none'} (hold = talk, tap = hands-free)")
        return

    if args.command == "daemon":
        from omarum.daemon import run_daemon

        try:
            asyncio.run(run_daemon())
        except KeyboardInterrupt:
            pass
        return

    # Starting a session loads Whisper and the voice, which can take several seconds.
    timeout = 2.0 if args.command in ("status", "reload") else 20.0
    try:
        reply = send_command(args.command, SOCKET_PATH, timeout=timeout)
    except DaemonNotRunning:
        print("omarum: daemon not running (start it with: omarum daemon)", file=sys.stderr)
        sys.exit(1)
    except TimeoutError:
        print("omarum: daemon not responding", file=sys.stderr)
        sys.exit(1)
    line = reply.get("state", "?")
    if reply.get("reason"):
        line += f" ({reply['reason']})"
    print(line)
    sys.exit(0 if reply.get("ok") else 1)


if __name__ == "__main__":
    main()
