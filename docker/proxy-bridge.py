#!/usr/bin/env python3
"""Bridge a host-local proxy onto a Docker bridge IP.

This keeps the upstream proxy bound to 127.0.0.1 on the host while exposing a
single TCP listener on the Docker bridge gateway address for containers.
"""

from __future__ import annotations

import argparse
import logging
import signal
import socket
import socketserver
import threading


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", required=True)
    parser.add_argument("--listen-port", required=True, type=int)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", required=True, type=int)
    return parser.parse_args()


class ThreadedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ProxyHandler(socketserver.BaseRequestHandler):
    target_host: str
    target_port: int

    def handle(self) -> None:
        upstream = socket.create_connection((self.target_host, self.target_port), timeout=10)
        upstream.settimeout(None)
        self.request.settimeout(None)

        threads = [
            threading.Thread(target=self._pipe, args=(self.request, upstream), daemon=True),
            threading.Thread(target=self._pipe, args=(upstream, self.request), daemon=True),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    @staticmethod
    def _pipe(source: socket.socket, destination: socket.socket) -> None:
        try:
            while True:
                chunk = source.recv(65536)
                if not chunk:
                    break
                destination.sendall(chunk)
        except OSError:
            pass
        finally:
            try:
                destination.shutdown(socket.SHUT_WR)
            except OSError:
                pass
            try:
                source.close()
            except OSError:
                pass


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    handler = type(
        "ConfiguredProxyHandler",
        (ProxyHandler,),
        {"target_host": args.target_host, "target_port": args.target_port},
    )

    with ThreadedTCPServer((args.listen_host, args.listen_port), handler) as server:
        logging.info(
            "proxy bridge listening on %s:%s -> %s:%s",
            args.listen_host,
            args.listen_port,
            args.target_host,
            args.target_port,
        )

        stop_event = threading.Event()

        def _shutdown(_signum: int, _frame: object) -> None:
            stop_event.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        try:
            server.serve_forever()
        finally:
            stop_event.set()
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
