"""Real file/command/web/browser/screenshot/API tools; MCP uses the official SDK."""
import asyncio
import os
import subprocess
import tempfile
import time
import webbrowser
from contextlib import AsyncExitStack
from pathlib import Path
from urllib.parse import urlparse, quote, urljoin
from xml.etree import ElementTree as ET
import httpx
from gamenext.infrastructure.document_reader import read_document
from gamenext.infrastructure.windows_folders import known_folder


def validate_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use uma URL HTTP/HTTPS sem credenciais embutidas")
    return value


def file_path(value):
    if not value or not str(value).strip():
        raise ValueError("Informe um caminho absoluto do Windows ou Downloads/Desktop/Documentos.")
    text = str(value).strip()
    special = known_folder(text)
    if special is not None:
        path = special
    else:
        # Support relative subpaths under known aliases such as "Desktop/jogo.html"
        parts = Path(text).parts
        alias = known_folder(parts[0]) if parts else None
        path = alias.joinpath(*parts[1:]) if alias is not None else Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError("Use um caminho absoluto do Windows ou Downloads/Desktop/Documentos.")
    path = path.resolve()
    lowered = {part.lower() for part in path.parts}
    if lowered.intersection({".ssh", ".aws", ".azure", "credentials", "vault", "protect"}) or path.name.lower() in {
        ".env", "id_ed25519", "id_rsa", "login data", "cookies", "web data",
    }:
        raise PermissionError("Armazenamentos de credenciais não são expostos ao modelo")
    return path


def computer(args):
    action = args["action"]
    if action == "run_command":
        command = (args.get("command") or "").strip()
        if not command:
            raise ValueError("Informe o campo command para executar um comando.")
        cwd = str(file_path(args["cwd"])) if args.get("cwd") else None
        if os.name == "nt":
            utf8_prefix = (
                "[Console]::InputEncoding=[Text.Encoding]::UTF8; "
                "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                "$OutputEncoding=[Text.Encoding]::UTF8; "
                "chcp 65001 > $null; "
            )
            shell = ["powershell", "-NoProfile", "-Command", utf8_prefix + command]
        else:
            shell = ["sh", "-c", command]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            shell,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            creationflags=flags,
        )
        return {
            "command": command,
            "cwd": cwd or os.getcwd(),
            "returncode": result.returncode,
            "stdout": result.stdout[-16000:],
            "stderr": result.stderr[-8000:],
        }

    if action == "list" and not args.get("path"):
        import psutil
        return {"drives": [partition.mountpoint for partition in psutil.disk_partitions()]}

    path = file_path(args.get("path", ""))
    if action == "open_folder":
        if not path.is_dir():
            raise ValueError("A pasta não existe ou está inacessível.")
        if os.name != "nt":
            raise OSError("Abrir no Explorador requer Windows.")
        os.startfile(str(path), "open")
        return {"opened_folder": str(path)}

    if action == "open_file":
        if not path.exists():
            raise ValueError("O arquivo não existe ou está inacessível.")
        if os.name != "nt":
            raise OSError("Abrir arquivo requer Windows.")
        os.startfile(str(path), "open")
        return {"opened_file": str(path)}

    if action == "mkdir":
        path.mkdir(parents=True, exist_ok=True)
        return {"created_folder": str(path)}

    if action == "list":
        entries = []
        with os.scandir(path) as iterator:
            for entry in iterator:
                entries.append({"name": entry.name, "directory": entry.is_dir(follow_symlinks=False)})
                if len(entries) >= 500:
                    break
        return {"path": str(path), "entries": entries, "count": len(entries)}

    if action == "read":
        return {"path": str(path), "content": read_document(path, 24000)}

    if action == "search":
        query = args.get("query", "").lower()
        if not query:
            raise ValueError("Informe query para buscar nomes")
        found, count = [], 0
        deadline = time.monotonic() + 25
        for root, dirs, files in os.walk(path, followlinks=False):
            dirs[:] = [
                d for d in dirs
                if d.lower() not in {"node_modules", ".git", "$recycle.bin", "system volume information"}
                and not (Path(root) / d).is_symlink()
            ]
            for name in dirs + files:
                count += 1
                if query in name.lower():
                    found.append(str(Path(root) / name))
                if len(found) >= 200 or count >= 100000 or time.monotonic() > deadline:
                    return {"matches": found, "limited": True}
        return {"matches": found, "limited": False}

    if action == "write":
        content = args.get("content")
        if not isinstance(content, str) or len(content) > 2_000_000:
            raise ValueError("Texto deve ter até 2.000.000 caracteres")
        path.parent.mkdir(parents=True, exist_ok=True)
        old = path.read_bytes() if path.exists() else None
        backup = None
        if old is not None and len(old) <= 25_000_000:
            backup = path.with_name(path.name + ".gamenext-backup")
            backup.write_bytes(old)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, prefix=".gamenext-") as temporary:
            temporary.write(content.encode("utf-8"))
            temp_path = Path(temporary.name)
        try:
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)
        return {"written": str(path), "characters": len(content), "backup": str(backup) if backup else None}

    raise ValueError("Ação de arquivos desconhecida")


class ToolRuntime:
    def __init__(self, config, data_dir):
        self.config = config
        self.data_dir = Path(data_dir)
        self.browser = None
        self.page = None
        self.playwright = None
        self.sessions = {}
        self.stack = AsyncExitStack()

    async def internet(self, args):
        from bs4 import BeautifulSoup
        action = args["action"]
        if action == "open":
            url = validate_url(args["url"])
            opened = await asyncio.to_thread(webbrowser.open, url)
            return {"url": url, "browser_open_requested": opened}
        if action in {"read", "search"}:
            url = validate_url(args["url"]) if action == "read" else "https://www.bing.com/search?format=rss&q=" + quote(args["query"])
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                max_redirects=6,
                headers={"User-Agent": "GameNext/0.4 local-assistant"},
            ) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 4_000_000:
                            break
                        chunks.append(chunk)
                    raw = b"".join(chunks)
            if action == "search":
                root = ET.fromstring(raw)
                return {
                    "results": [
                        {"title": item.findtext("title"), "url": item.findtext("link"), "summary": item.findtext("description")}
                        for item in root.findall(".//item")[:10]
                    ]
                }
            soup = BeautifulSoup(raw, "html.parser")
            for node in soup(["script", "style", "nav", "footer", "noscript"]):
                node.decompose()
            return {
                "url": str(response.url),
                "text": soup.get_text(" ", strip=True)[:20000],
                "links": [
                    {"text": a.get_text(strip=True)[:100], "url": urljoin(str(response.url), a.get("href", ""))}
                    for a in soup.find_all("a", href=True)[:20]
                ],
            }
        if not self.page:
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(channel="msedge", headless=False)
            self.page = await self.browser.new_page()
            self.page.set_default_timeout(20000)
        if action == "navigate":
            await self.page.goto(validate_url(args["url"]), wait_until="domcontentloaded", timeout=30000)
        elif action == "click":
            await self.page.locator(args["selector"]).first.click()
        elif action == "type":
            await self.page.locator(args["selector"]).first.fill(args["text"])
        elif action != "content":
            raise ValueError("Ação de navegador desconhecida")
        return {"url": self.page.url, "title": await self.page.title(), "text": (await self.page.locator("body").inner_text())[:20000]}

    async def mcp(self, args):
        from gamenext.infrastructure.mcp_connection import McpConnection
        servers = self.config.get("mcp_servers", {})
        if args["action"] == "servers":
            return {"servers": list(servers)}
        name = args.get("server", "")
        if name not in servers:
            raise ValueError("Servidor MCP não configurado")
        if name in self.sessions and self.sessions[name].definition != servers[name]:
            await self.sessions.pop(name).close()
        if name not in self.sessions:
            self.sessions[name] = McpConnection(servers[name])
        return await self.sessions[name].request(args)

    async def api(self, args):
        profiles = self.config.get("api_profiles", {})
        profile = args.get("profile")
        if not profile:
            return {"profiles": [{"name": name, "url": value["url"]} for name, value in profiles.items()]}
        if profile not in profiles:
            raise ValueError("Perfil API não configurado")
        item = profiles[profile]
        base = validate_url(item["url"])
        url = urljoin(base.rstrip("/") + "/", args.get("path", "").lstrip("/"))
        if urlparse(url).netloc != urlparse(base).netloc or not url.startswith(base.rstrip("/") + "/"):
            raise ValueError("O caminho deve permanecer no endpoint configurado")
        headers = {}
        token = None
        if item.get("credential"):
            import keyring
            token = keyring.get_password("GameNext", item["credential"])
            if token:
                headers["Authorization"] = "Bearer " + token
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            async with client.stream(args.get("method", "GET"), url, headers=headers, json=args.get("body")) as response:
                output = bytearray()
                async for chunk in response.aiter_bytes():
                    output.extend(chunk)
                    if len(output) > 40000:
                        break
        text = bytes(output[:40000]).decode("utf-8", errors="replace")
        if token:
            text = text.replace(token, "[redigido]")
        return {"status": response.status_code, "body": text[:20000], "url": url}

    async def execute(self, name, args):
        if name == "computer":
            return await asyncio.to_thread(computer, args)
        if name == "internet":
            return await self.internet(args)
        if name == "mcp":
            return await self.mcp(args)
        if name == "api":
            return await self.api(args)
        if name == "screenshot":
            from PIL import ImageGrab
            directory = self.data_dir / "artifacts"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"screen-{time.time_ns()}.png"
            image = await asyncio.to_thread(ImageGrab.grab, all_screens=True)
            await asyncio.to_thread(image.save, path)
            return {
                "artifact": str(path),
                "width": image.width,
                "height": image.height,
                "note": "Captura salva com sucesso.",
            }
        raise ValueError("Ferramenta desconhecida")

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        for connection in self.sessions.values():
            await connection.close()
        await self.stack.aclose()
