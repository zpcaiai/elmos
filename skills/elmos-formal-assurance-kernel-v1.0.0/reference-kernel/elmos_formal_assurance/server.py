from __future__ import annotations
import os
from wsgiref.simple_server import make_server
from .service import application

def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    with make_server(host, port, application) as server:
        server.serve_forever()

if __name__ == "__main__":
    main()
