"""Explicitly simulated inference; never invokes tools or accesses a model."""


def response(prompt: str, task_mode: bool, attachments: list[str]) -> str:
    if task_mode:
        return (
            "Preparei uma prévia do plano no painel de tarefas. Você pode pausar, retomar ou "
            "cancelar a simulação.\n\nNenhum arquivo foi alterado e nenhuma ferramenta foi executada. "
            "A conexão com modelos locais e ferramentas faz parte da próxima etapa."
        )
    if attachments:
        return (f"Você anexou {len(attachments)} arquivo(s). As referências ficaram salvas nesta conversa. "
                "Nesta demonstração, o conteúdo dos arquivos não é enviado nem analisado.")
    if any(word in prompt.lower() for word in ("código", "python", "script")):
        return 'Este é um exemplo estático de código Python. Expanda o bloco para copiar.\n\n```python\ndef iniciar():\n    return "Olá, GameNext"\n\nprint(iniciar())\n```'
    if any(word in prompt.lower() for word in ("godot", "blender", "jogo", "árvore")):
        return (
            "Podemos começar pela referência visual, definir o asset e preparar a integração "
            "no projeto. Use o modo Tarefas para visualizar um plano de exemplo.\n\n"
            "Blender e Godot ainda não estão conectados neste MVP."
        )
    return (
        "O GameNext está pronto para organizar suas conversas e planejar seu trabalho. "
        "O histórico é salvo apenas neste computador.\n\n"
        "Esta resposta é uma demonstração da interface. Nenhum modelo de IA está conectado ainda."
    )
