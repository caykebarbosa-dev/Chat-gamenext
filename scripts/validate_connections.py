"""Exercise real stdio MCP and a loopback API without external credentials."""
import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gamenext.infrastructure.tool_runtime import ToolRuntime


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"gamenext":"api-ok"}')

    def log_message(self, *args):
        pass


async def main():
    api = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    runtime = ToolRuntime({
        "mcp_servers": {"Local": {"command": sys.executable, "args": [str(ROOT / "src/gamenext/infrastructure/game_mcp_server.py"), "--blender", "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"]}},
        "api_profiles": {"Local": {"url": f"http://127.0.0.1:{api.server_port}/"}},
    }, ROOT / "output")
    try:
        listed = await runtime.execute("mcp", {"action": "list", "server": "Local"})
        print("MCP TOOLS", json.dumps(listed, ensure_ascii=False), flush=True)
        status = await runtime.execute("mcp", {"action": "call", "server": "Local", "tool": "platform_status"})
        print("MCP REAL STATUS", json.dumps(status, ensure_ascii=False), flush=True)
        result = await runtime.execute("api", {"profile": "Local", "path": "", "method": "GET"})
        assert "api-ok" in result["body"]
        print("API OK", result, flush=True)
    finally:
        await runtime.close()
        api.shutdown()


asyncio.run(main())
