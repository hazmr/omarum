"""`omarum daemon | toggle | start | stop | status`"""

from __future__ import annotations

import argparse
import asyncio
import sys

from omarum.ipc import SOCKET_PATH, DaemonNotRunning, send_command


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="omarum", description="Talk to Rum.")
    parser.add_argument("command", choices=["daemon", "toggle", "start", "stop", "status"])
    args = parser.parse_args(argv)

    if args.command == "daemon":
        from omarum.daemon import run_daemon

        try:
            asyncio.run(run_daemon())
        except KeyboardInterrupt:
            pass
        return

    # Starting a session loads Whisper and the voice, which can take several seconds.
    timeout = 2.0 if args.command == "status" else 20.0
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
