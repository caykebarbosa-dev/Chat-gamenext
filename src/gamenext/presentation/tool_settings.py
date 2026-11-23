"""Owner-managed tool freedom, tool toggles, MCP servers and API credential references."""
import json
import sys
import shutil
from pathlib import Path
from uuid import uuid4
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QCheckBox, QPlainTextEdit, QLineEdit, QHBoxLayout, QGridLayout, QFileDialog
from gamenext.presentation.components import label, button, vertical
from gamenext.presentation.containers import container, field_block
from gamenext.infrastructure.tool_runtime import validate_url


class ToolSettings(QWidget):
    policy_changed = pyqtSignal()

    def __init__(self, repository, controller):
        super().__init__()
        self.repository = repository
        outer = vertical(self, spacing=14)

        # Card 1: Autonomy & execution control
        policy_card = container()
        policy_box = vertical(policy_card, (18, 16, 18, 16), 10)
        policy_box.addWidget(label("Liberdade e autonomia das ferramentas", "sectionTitle"))
        policy_box.addWidget(label(
            "Controle se a IA pode acionar ferramentas livremente sempre que um pedido envolver arquivos, "
            "comandos, navegador, captura de tela, MCP ou APIs.",
            "silver",
            True,
        ))
        self.autonomous = QCheckBox("Modo autônomo · permitir que a IA use ferramentas livremente sem pedir confirmação")
        self.autonomous.setChecked(not repository.preference("tool_ask_changes", False))
        self.autonomous.toggled.connect(self.save)
        policy_box.addWidget(self.autonomous)
        policy_box.addWidget(label(
            "Desmarque acima se quiser aprovar manualmente escritas de arquivos, comandos, cliques no navegador ou chamadas MCP.",
            "muted",
            True,
        ))
        bar = QHBoxLayout()
        bar.setSpacing(10)
        stop_btn = button("Parar ferramentas em execução", controller.cancel)
        stop_btn.setObjectName("dangerControl")
        bar.addWidget(stop_btn)
        bar.addStretch()
        policy_box.addLayout(bar)
        outer.addWidget(policy_card)

        # Card 2: Individual tool switches in clean 2-column grid
        tools_card = container()
        tools_box = vertical(tools_card, (18, 16, 18, 16), 12)
        tools_box.addWidget(label("Ferramentas disponíveis para a IA", "sectionTitle"))
        tools_box.addWidget(label(
            "Todas as ferramentas marcadas ficam imediatamente disponíveis para o modelo local usar quando precisar.",
            "silver",
            True,
        ))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        enabled = repository.preference("tool_enabled", {})
        self.checks = {}
        items = [
            (
                "computer",
                "Arquivos, pastas e comandos",
                "Listar discos/pastas, buscar, ler documentos (texto, código, PDF, Word, planilhas), criar/editar arquivos, abrir no Windows e rodar comandos PowerShell.",
            ),
            (
                "internet",
                "Internet e navegador",
                "Pesquisar na web, ler conteúdo de páginas, abrir links no navegador padrão e controlar navegador Edge dedicado.",
            ),
            (
                "screenshot",
                "Captura de tela",
                "Capturar os monitores sob demanda durante a conversa e salvar PNG local.",
            ),
            (
                "mcp",
                "Conexões MCP (Blender, Godot e outros)",
                "Descobrir e chamar ferramentas reais expostas pelos servidores configurados na aba MCP.",
            ),
            (
                "api",
                "Conexões API HTTP",
                "Enviar requisições GET/POST/PUT/DELETE para endpoints configurados na aba API, usando tokens no cofre do Windows.",
            ),
        ]
        for idx, (name, title, description) in enumerate(items):
            cell = container("infoBanner")
            cell_layout = vertical(cell, (14, 12, 14, 12), 6)
            check = QCheckBox(title)
            check.setChecked(enabled.get(name, True))
            check.toggled.connect(self.save)
            self.checks[name] = check
            cell_layout.addWidget(check)
            cell_layout.addWidget(label(description, "silver", True))
            cell_layout.addStretch()
            grid.addWidget(cell, idx // 2, idx % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        tools_box.addLayout(grid)
        outer.addWidget(tools_card)

    def save(self):
        self.repository.set_preference("tool_enabled", {name: check.isChecked() for name, check in self.checks.items()})
        self.repository.set_preference("tool_ask_changes", not self.autonomous.isChecked())
        self.policy_changed.emit()


class ConnectionSettings(QWidget):
    def __init__(self, repository, controller, kind):
        super().__init__()
        self.repository, self.controller, self.kind = repository, controller, kind
        self.key = "mcp_servers" if kind == "mcp" else "api_profiles"
        if kind == "mcp" and repository.preference(self.key) is None:
            script = Path(__file__).resolve().parents[1] / "infrastructure/game_mcp_server.py"
            args = [str(script)]
            candidates = list(Path("C:/Program Files/Blender Foundation").glob("Blender */blender.exe"))
            if candidates:
                args += ["--blender", str(sorted(candidates)[-1])]
            godot = shutil.which("godot") or shutil.which("godot4")
            if godot:
                args += ["--godot", godot]
            repository.set_preference(self.key, {"BlenderGodot": {"transport": "stdio", "command": sys.executable, "args": args}})
        self.test_id = None
        outer = vertical(self, spacing=14)

        card = container()
        content = vertical(card, (18, 16, 18, 16), 12)
        content.addWidget(label("Servidores MCP" if kind == "mcp" else "Perfis de API", "sectionTitle"))
        description = (
            'Configure servidores por nome em JSON. Exemplo stdio: {"Blender": {"transport":"stdio", "command":"python", "args":["C:/mcp/server.py"]}}. '
            'Exemplo HTTP: {"Godot": {"transport":"http", "url":"http://127.0.0.1:8000/mcp"}}.'
            if kind == "mcp"
            else 'Configure endpoints por nome em JSON: {"MinhaAPI": {"url":"https://api.exemplo.com/v1/", "credential":"minha-api"}}. '
                 'O campo credential referencia o cofre do Windows (não cole chaves diretamente no JSON).'
        )
        content.addWidget(label(description, "silver", True))
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(json.dumps(repository.preference(self.key, {}), ensure_ascii=False, indent=2))
        self.editor.setMinimumHeight(180)
        self.editor.setMaximumHeight(260)
        content.addWidget(self.editor)
        if kind == "mcp":
            platforms = QHBoxLayout()
            platforms.setSpacing(10)
            platforms.addWidget(button("Selecionar Blender.exe", lambda: self.pick_platform("blender")))
            platforms.addWidget(button("Selecionar Godot.exe", lambda: self.pick_platform("godot")))
            platforms.addStretch()
            content.addLayout(platforms)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Nome da conexão para testar (ex.: BlenderGodot)")
        content.addWidget(field_block("Testar conexão", self.name))
        actions = QHBoxLayout()
        actions.setSpacing(10)
        save_btn = button("Salvar conexões", self.save)
        save_btn.setObjectName("primaryControl")
        actions.addWidget(save_btn)
        actions.addWidget(button("Testar conexão", self.test))
        actions.addStretch()
        content.addLayout(actions)
        self.status = label("Nenhuma conexão testada", "statusBadge", True)
        content.addWidget(self.status)
        outer.addWidget(card)

        cred_card = container()
        cred_content = vertical(cred_card, (18, 16, 18, 16), 12)
        cred_content.addWidget(label("Credenciais no Cofre do Windows", "sectionTitle"))
        cred_content.addWidget(label("Armazene tokens Bearer com segurança fora do histórico e dos arquivos JSON.", "silver", True))
        self.credential = QLineEdit()
        self.credential.setPlaceholderText("Ex.: minha-api")
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText("Token Bearer")
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(field_block("Referência da credencial", self.credential), 1)
        row.addWidget(field_block("Token Bearer", self.secret), 1)
        cred_content.addLayout(row)
        cred_actions = QHBoxLayout()
        cred_actions.addWidget(button("Salvar token no cofre", self.save_secret))
        cred_actions.addStretch()
        cred_content.addLayout(cred_actions)
        outer.addWidget(cred_card)

        controller.result.connect(self.test_result)

    def save(self):
        try:
            data = json.loads(self.editor.toPlainText())
            if not isinstance(data, dict):
                raise ValueError("Use um objeto JSON por nome de conexão")
            if len(data) > 50:
                raise ValueError("Máximo de 50 conexões")
            for name, config in data.items():
                if not isinstance(config, dict):
                    raise ValueError("Cada conexão precisa de um objeto de configuração")
                if any(key.lower() in {"token", "api_key", "password", "headers", "env"} for key in config):
                    raise ValueError("Use credential para referenciar o cofre; não cole segredos no JSON")
                if self.kind == "mcp" and config.get("transport", "stdio") == "stdio":
                    if (
                        not isinstance(config.get("command"), str)
                        or not isinstance(config.get("args", []), list)
                        or not all(isinstance(arg, str) for arg in config.get("args", []))
                    ):
                        raise ValueError("MCP stdio exige command e args como lista de strings")
                else:
                    validate_url(config["url"])
            self.repository.set_preference(self.key, data)
            self.status.setText("Conexões salvas com sucesso.")
            return True
        except (ValueError, KeyError, TypeError) as error:
            self.status.setText(str(error))
            return False

    def save_secret(self):
        try:
            import keyring
            if not self.credential.text().strip() or not self.secret.text():
                raise ValueError("Preencha a referência e o token")
            keyring.set_password("GameNext", self.credential.text().strip(), self.secret.text())
            self.secret.clear()
            self.status.setText("Token salvo no cofre de credenciais do Windows")
        except Exception as error:
            self.status.setText("Não foi possível salvar a credencial: " + str(error))

    def pick_platform(self, kind):
        path, _ = QFileDialog.getOpenFileName(self, f"Executável {kind}", "", "Executável (*.exe)")
        if not path:
            return
        try:
            data = json.loads(self.editor.toPlainText())
            script = Path(__file__).resolve().parents[1] / "infrastructure/game_mcp_server.py"
            config = data.setdefault("BlenderGodot", {"transport": "stdio", "command": sys.executable, "args": [str(script)]})
            args = config["args"]
            flag = "--" + kind
            if flag in args:
                args[args.index(flag) + 1] = path
            else:
                args.extend([flag, path])
            self.editor.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
            self.save()
        except (ValueError, KeyError, TypeError) as error:
            self.status.setText(str(error))

    def test(self):
        if not self.save():
            return
        if self.controller.pending or getattr(self.controller, "agent_busy", lambda: False)():
            self.status.setText("Aguarde o chat ou a ferramenta em execução")
            return
        name = self.name.text().strip()
        args = {"action": "list", "server": name} if self.kind == "mcp" else {"profile": name, "method": "GET", "path": ""}
        self.test_id = "connection_test_" + str(uuid4())
        self.controller.execute({"id": self.test_id, "function": {"name": self.kind, "arguments": json.dumps(args)}})
        self.status.setText("Testando conexão real…")

    def test_result(self, event):
        if event["call"].get("id") == self.test_id:
            self.status.setText(json.dumps(event.get("result") if event.get("ok") else event.get("error"), ensure_ascii=False)[:1800])
