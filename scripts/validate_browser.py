"""Exercise dedicated browser navigation, filling, click and reading on a local fixture."""
import asyncio
import sys
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gamenext.infrastructure.tool_runtime import ToolRuntime


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'<title>GameNext browser test</title><input id="message"><button id="apply" onclick="document.querySelector(\'#result\').textContent=document.querySelector(\'#message\').value">Apply</button><p id="result"></p>')

    def log_message(self, *args):
        pass


async def main():
    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    runtime = ToolRuntime({}, ROOT / "output")
    try:
        await runtime.internet({"action": "navigate", "url": f"http://127.0.0.1:{http.server_port}/"})
        await runtime.internet({"action": "type", "selector": "#message", "text": "GameNext browser OK"})
        result = await runtime.internet({"action": "click", "selector": "#apply"})
        assert "GameNext browser OK" in result["text"]
        print("BROWSER REAL OK", flush=True)
    finally:
        await runtime.close()
        http.shutdown()


asyncio.run(main())
