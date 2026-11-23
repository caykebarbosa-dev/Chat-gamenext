"""Keep each MCP transport's async contexts owned by one persistent task."""
import asyncio
from contextlib import AsyncExitStack, suppress


class McpConnection:
    def __init__(self, definition):
        self.definition = definition
        self.queue = asyncio.Queue()
        self.task = asyncio.create_task(self.run())
        self.error = None

    async def request(self, arguments):
        if self.error:
            raise RuntimeError(self.error)
        future = asyncio.get_running_loop().create_future()
        await self.queue.put((arguments, future))
        return await future

    async def run(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamablehttp_client
        from gamenext.infrastructure.tool_runtime import validate_url
        active = None
        try:
            async with AsyncExitStack() as stack:
                config = self.definition
                if config.get("transport", "stdio") == "stdio":
                    params = StdioServerParameters(command=config["command"], args=config.get("args", []), cwd=config.get("cwd"))
                    read, write = await stack.enter_async_context(stdio_client(params))
                else:
                    headers = {}
                    if config.get("credential"):
                        import keyring
                        token = keyring.get_password("GameNext", config["credential"])
                        if token:
                            headers["Authorization"] = "Bearer " + token
                    read, write, _ = await stack.enter_async_context(streamablehttp_client(validate_url(config["url"]), headers=headers))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                while True:
                    item = await self.queue.get()
                    if item is None:
                        break
                    args, active = item
                    try:
                        if args["action"] == "list":
                            response = await session.list_tools()
                            result = {"tools": [{"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema} for tool in response.tools][:40]}
                        elif args["action"] == "call":
                            response = await session.call_tool(args["tool"], args.get("arguments", {}))
                            result = {"isError": response.isError, "content": [block.text[:7000] if block.type == "text" else f"[conteúdo MCP do tipo {block.type}]" for block in response.content]}
                        else:
                            raise ValueError("Ação MCP desconhecida")
                        if not active.done():
                            active.set_result(result)
                    except Exception as error:
                        if not active.done():
                            active.set_exception(error)
                    active = None
        except Exception as error:
            self.error = str(error)
            if active and not active.done():
                active.set_exception(RuntimeError(self.error))
            while not self.queue.empty():
                item = self.queue.get_nowait()
                if item and not item[1].done():
                    item[1].set_exception(RuntimeError(self.error))

    async def close(self):
        if self.task.done():
            return
        await self.queue.put(None)
        try:
            await asyncio.wait_for(asyncio.shield(self.task), 3)
        except asyncio.TimeoutError:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
