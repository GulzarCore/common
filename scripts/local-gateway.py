from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import os

# Layout: <workspace>/common/scripts/local-gateway.py and <workspace>/frontend/index.html
ROOT = Path(__file__).resolve().parents[2]
PORT = int(os.environ.get("GATEWAY_PORT", "3001"))
ROUTES = {
    "/api/kotlin1": "http://127.0.0.1:8081",
    "/api/kotlin2": "http://127.0.0.1:8084",
    "/api/python3": "http://127.0.0.1:8086",
    "/api/kotlin1-python": "http://127.0.0.1:8087",
}


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            index = ROOT / "frontend" / "index.html"
            if not index.is_file():
                self.send_bytes(500, b'{"error":"frontend/index.html not found"}', "application/json")
                return
            self.send_bytes(200, index.read_bytes(), "text/html; charset=utf-8")
            return

        if path == "/health":
            self.send_bytes(200, b'{"status":"ok","service":"common-gateway"}', "application/json")
            return

        # Longest-prefix matching avoids route collisions as the gateway grows.
        for prefix, upstream in sorted(ROUTES.items(), key=lambda item: len(item[0]), reverse=True):
            if path == prefix or path.startswith(prefix + "/"):
                suffix = path[len(prefix):] or "/health"
                target = upstream + suffix
                print(f"[gateway] {path} -> {target}", flush=True)
                try:
                    with urlopen(Request(target), timeout=3) as response:
                        self.send_bytes(
                            response.status,
                            response.read(),
                            response.headers.get("Content-Type", "application/json"),
                        )
                except HTTPError as error:
                    print(f"[gateway] Upstream HTTP {error.code}: {target}", flush=True)
                    self.send_bytes(error.code, error.read(), error.headers.get("Content-Type", "application/json"))
                except (URLError, TimeoutError, OSError) as error:
                    print(f"[gateway] Upstream connection failed: {target}: {error}", flush=True)
                    payload = json.dumps({"status": "unavailable", "upstream": prefix}).encode()
                    self.send_bytes(503, payload, "application/json")
                return

        print(f"[gateway] No route matched: {path}", flush=True)
        self.send_bytes(404, b'{"error":"not found"}', "application/json")

    def log_message(self, fmt, *args):
        print("[gateway] " + fmt % args)


if __name__ == "__main__":
    print(f"Common frontend: http://localhost:{PORT}", flush=True)
    print(f"Frontend file: {ROOT / 'frontend' / 'index.html'}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
