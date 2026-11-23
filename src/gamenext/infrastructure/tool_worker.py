"""Isolated tool process, sequential UTF-8 JSON requests and generous timeouts."""
import asyncio
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gamenext.infrastructure.tool_runtime import ToolRuntime


async def main():
    runtime = ToolRuntime({}, sys.argv[1])
    try:
        while True:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                break
            request = json.loads(line)
            runtime.config = request.get("config", {})
            try:
                result = await asyncio.wait_for(runtime.execute(request["tool"], request["arguments"]), timeout=160)
                response = {"id": request["id"], "ok": True, "result": result}
            except Exception as error:
                response = {"id": request["id"], "ok": False, "error": str(error)[:2000]}
            print(json.dumps(response, ensure_ascii=True), flush=True)
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
