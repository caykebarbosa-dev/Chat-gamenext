"""Read-only smoke checks of real tool integrations; no model required."""
import sys
import json
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gamenext.infrastructure.tool_runtime import ToolRuntime


async def main():
    runtime = ToolRuntime({}, ROOT / "output")
    for name, args in [
        ("computer", {"action": "list", "path": str(ROOT)}),
        ("computer", {"action": "read", "path": str(ROOT / "README.md")}),
        ("internet", {"action": "search", "query": "Godot official documentation"}),
        ("internet", {"action": "read", "url": "https://docs.godotengine.org"}),
        ("api", {}), ("mcp", {"action": "servers"}), ("screenshot", {}),
    ]:
        try:
            print(name, json.dumps(await runtime.execute(name, args), ensure_ascii=False)[:1000], flush=True)
        except Exception as error:
            print(name, "ERROR", str(error), flush=True)
    await runtime.close()


asyncio.run(main())
