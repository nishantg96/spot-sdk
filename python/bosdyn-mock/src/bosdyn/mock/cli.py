"""Command line entry point for the mock services."""
from __future__ import annotations

import argparse
import logging
import signal
import sys
from typing import Dict

from .server import MockRobotServer


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start a mock Spot robot server")
    parser.add_argument("--host", default="0.0.0.0", help="Address to bind")
    parser.add_argument("--port", type=int, default=50051, help="Port for all services")
    parser.add_argument("--username", default="admin", help="Default username")
    parser.add_argument("--password", default="password", help="Default password")
    parser.add_argument("--resource", action="append", default=["body"],
                        help="Lease resources to advertise")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    credentials: Dict[str, str] = {args.username: args.password}
    server = MockRobotServer(host=args.host, port=args.port, credentials=credentials,
                             resources=args.resource)
    server.start()

    def _handle_signal(signum, frame):  # pylint: disable=unused-argument
        logging.info("Received signal %s, shutting down", signum)
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        server.block_until_shutdown()
    except KeyboardInterrupt:
        _handle_signal(signal.SIGINT, None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
