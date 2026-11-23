"""Bundled MCP bridge for installed Blender and Godot, using their real CLI APIs."""
import argparse
import subprocess
import tempfile
from pathlib import Path
from mcp.server.fastmcp import FastMCP

server = FastMCP("GameNext game tools")
configuration = {"blender": "", "godot": ""}


def executable(kind):
    path = Path(configuration[kind])
    if not path.is_file():
        raise ValueError(f"Executável {kind} não configurado no servidor MCP")
    return str(path)


@server.tool()
def platform_status() -> dict:
    """Detecta versões reais de Blender/Godot; não abre nem modifica projetos."""
    results = {}
    for kind in configuration:
        try:
            result = subprocess.run([executable(kind), "--version"], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
            results[kind] = {"executable": configuration[kind], "version": result.stdout[:1200], "code": result.returncode}
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            results[kind] = {"error": str(error)}
    return results


@server.tool()
def blender_python(script: str) -> dict:
    """Executa Python bpy real em uma instância Blender headless separada. Não controla uma cena aberta. Use caminhos absolutos no script para salvar/renderizar/exportar; nunca alegue sucesso sem verificar logs/arquivos."""
    if len(script) > 100000:
        raise ValueError("Script excessivo")
    with tempfile.TemporaryDirectory(prefix="gamenext-blender-") as directory:
        path = Path(directory) / "task.py"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run([executable("blender"), "--background", "--python-exit-code", "1", "--python", str(path)],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        return {"code": result.returncode, "stdout": result.stdout[-6000:], "stderr": result.stderr[-2000:]}


@server.tool()
def godot_validate(project_path: str) -> dict:
    """Abre/importa um projeto Godot em headless e verifica erros. Pode atualizar o cache .godot; não edita scripts ou cenas."""
    project = Path(project_path).resolve()
    if not (project / "project.godot").is_file():
        raise ValueError("project.godot não encontrado")
    result = subprocess.run([executable("godot"), "--headless", "--path", str(project), "--editor", "--quit"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return {"code": result.returncode, "stdout": result.stdout[-5000:], "stderr": result.stderr[-3000:]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", default="")
    parser.add_argument("--godot", default="")
    options = parser.parse_args()
    configuration.update(blender=options.blender, godot=options.godot)
    server.run(transport="stdio")
