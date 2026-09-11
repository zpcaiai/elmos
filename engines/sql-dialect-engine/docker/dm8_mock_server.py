"""Lightweight DM8 mock server for CDC compatibility test environments."""
from __future__ import annotations

import socket
import sys
import threading


def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    try:
        conn.settimeout(10.0)
        while True:
            data = conn.recv(1024)
            if not data:
                break
            # Reply with an ACK or mock response
            if b"PING" in data or b"ping" in data:
                conn.sendall(b"PONG\n")
            elif b"SELECT 1" in data or b"select 1" in data:
                conn.sendall(b"1\n")
            else:
                conn.sendall(b"DM8_MOCK_OK\n")
    except Exception:
        pass
    finally:
        conn.close()


def main() -> None:
    port = 5236
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(128)
    print(f"[DM8 Mock Server] Listening on port {port}...")
    while True:
        try:
            conn, addr = server.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error accepting connection: {e}", file=sys.stderr)
    server.close()


if __name__ == "__main__":
    main()
