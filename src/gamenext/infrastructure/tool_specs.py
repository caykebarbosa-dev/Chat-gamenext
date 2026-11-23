"""Compact native function contracts sent to the local model."""


def spec(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


STRING = {"type": "string"}
TOOLS = [
    spec(
        "computer",
        "Opera arquivos, pastas e comandos no Windows. Ações: open_folder (abre pasta no Explorador), open_file (abre arquivo no app padrão), list (lista arquivos; sem path lista discos), search (busca por nome usando path e query), read (lê arquivo/documento), write (cria/edita arquivo com path e content), mkdir (cria pasta), run_command (executa comando PowerShell usando command e cwd opcional). Aceita caminho absoluto ou Downloads/Desktop/Documentos.",
        {
            "action": {
                "type": "string",
                "enum": ["open_folder", "open_file", "list", "search", "read", "write", "mkdir", "run_command"],
            },
            "path": STRING,
            "query": STRING,
            "content": STRING,
            "command": STRING,
            "cwd": STRING,
        },
        ["action"],
    ),
    spec(
        "internet",
        "Pesquisa na web, lê páginas, abre URL no navegador do Windows ou controla navegador dedicado (navigate/click/type/content). Use search antes de adivinhar URLs.",
        {
            "action": {
                "type": "string",
                "enum": ["search", "read", "open", "navigate", "click", "type", "content"],
            },
            "url": STRING,
            "query": STRING,
            "selector": STRING,
            "text": STRING,
        },
        ["action"],
    ),
    spec(
        "screenshot",
        "Captura a tela do Windows agora e salva um arquivo PNG real. Retorna o caminho salvo.",
        {},
        [],
    ),
    spec(
        "mcp",
        "Conecta a servidores MCP configurados (incluindo Blender e Godot), lista ferramentas ou chama uma ferramenta real. Use action=servers ou list antes de call.",
        {
            "action": {"type": "string", "enum": ["servers", "list", "call"]},
            "server": STRING,
            "tool": STRING,
            "arguments": {"type": "object"},
        },
        ["action"],
    ),
    spec(
        "api",
        "Faz requisição HTTP a um perfil API configurado pelo proprietário. Sem profile lista perfis disponíveis; use path relativo ao endpoint.",
        {
            "profile": STRING,
            "path": STRING,
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
            "body": {"type": "object"},
        },
        [],
    ),
]
