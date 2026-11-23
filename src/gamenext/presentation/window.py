"""Composition of the sidebar, unified Local + Kilo chat, pages and live VoiceBeam."""
import json
from pathlib import Path
from PyQt6.QtCore import Qt, QProcess, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QLineEdit,
    QListWidget, QListWidgetItem, QScrollArea, QInputDialog,
    QMessageBox, QFileDialog, QMenu, QDialog, QSizePolicy,
)
from gamenext.application.chat_controller import ChatController
from gamenext.presentation.components import label, button, vertical
from gamenext.presentation.composer import Composer
from gamenext.presentation.messages import MessageView
from gamenext.presentation.settings import SettingsPage
from gamenext.presentation.tasks import TaskPanel
from gamenext.presentation.kilo_model_dialog import KiloCatalogDialog
from gamenext.infrastructure.local_backend import LocalBackend
from gamenext.infrastructure.kilo_backend import KiloBackend
from gamenext.infrastructure.kilo_api import (
    DEFAULT_USD_TO_BRL,
    load_enabled_kilo_ids,
    load_kilo_models,
)
from gamenext.application.audio_controller import AudioController
from gamenext.presentation.audio_settings import MicrophoneDialog
from gamenext.application.tool_controller import ToolController


class MainWindow(QMainWindow):
    def __init__(self, repository, data_dir, demo=False):
        super().__init__()
        self.repository = repository
        self.demo = demo
        self.backend = None if demo else LocalBackend(data_dir, self)
        self.kilo_backend = None if demo else KiloBackend(repository, self)
        self.audio = AudioController(repository, self)
        self.tools = ToolController(repository, data_dir, self)
        self.controller = ChatController(
            repository,
            self.backend,
            self.tools if not demo else None,
            kilo_backend=self.kilo_backend,
        )
        self.tools.agent_busy = lambda: self.controller.active
        self.current_id = None
        self.streaming_view = None
        self.collapsed = False
        self.task_requested = False
        self.pending_model_path = None
        self.pending_send = None
        self.local_catalog = []

        self.setWindowTitle("GameNext · 0.4.0")
        self.resize(1440, 900)
        self.setMinimumSize(960, 640)
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(196)
        left = vertical(self.sidebar, (12, 18, 12, 16), 6)
        self.brand = label("GameNext", "brand")
        top = QHBoxLayout()
        top.addWidget(self.brand)
        top.addStretch()
        top.addWidget(button("", self.toggle_sidebar, "panel", "Recolher ou expandir menu"))
        left.addLayout(top)
        left.addSpacing(22)
        self.nav = []
        for index, (title, symbol) in enumerate((("Chat", "chat"), ("Estúdio", "studio"), ("Configurações", "settings"))):
            nav = button(title, lambda checked=False, i=index: self.navigate(i), symbol)
            nav.setCheckable(True)
            self.nav.append(nav)
            left.addWidget(nav)
        left.addSpacing(24)
        self.new_button = button("Nova conversa", self.new_conversation, "plus")
        left.addWidget(self.new_button)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar conversas")
        self.search.setAccessibleName("Buscar no histórico")
        self.search.textChanged.connect(self.refresh_history)
        left.addWidget(self.search)
        left.addSpacing(12)
        self.history_title = label("CONVERSAS", "muted")
        left.addWidget(self.history_title)
        self.history = QListWidget()
        self.history.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.history.itemClicked.connect(lambda item: self.open_conversation(item.data(Qt.ItemDataRole.UserRole)))
        self.history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self.history_menu)
        left.addWidget(self.history, 1)
        self.local_status = label("Local · modelo não carregado", "silver")
        self.permissions = label("", "muted")
        left.addWidget(self.local_status)
        left.addWidget(self.permissions)
        shell.addWidget(self.sidebar)

        self.pages = QStackedWidget()
        shell.addWidget(self.pages, 1)

        self.chat = QWidget()
        chat_layout = vertical(self.chat, (28, 20, 28, 16), 10)
        header = QHBoxLayout()
        self.title = label("Nova conversa")
        header.addWidget(self.title, 1)
        header.addWidget(button("", self.export, "export", "Exportar conversa"))
        self.task_button = button("Tarefas", self.toggle_tasks, "tasks")
        header.addWidget(self.task_button)
        chat_layout.addLayout(header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transcript = QWidget()
        self.transcript.setMaximumWidth(860)
        self.messages_layout = vertical(self.transcript, (8, 18, 8, 18), 4)
        self.scroll.setWidget(self.transcript)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        chat_layout.addWidget(self.scroll, 1)
        self.composer = Composer()
        self.composer.setMaximumWidth(880)
        chat_layout.addWidget(self.composer, 0, Qt.AlignmentFlag.AlignHCenter)
        self.composer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.composer.submit.connect(self.send)
        self.composer.preference_changed.connect(self.save_composer)
        self.composer.microphone_clicked.connect(self.microphone_action)
        self.composer.kilo_catalog_clicked.connect(self.open_kilo_catalog)
        footer = label("Escolha um modelo Local (GGUF) ou Kilo Gateway abaixo para conversar.", "muted")
        self.footer = footer
        self.footer.setWordWrap(True)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chat_layout.addWidget(footer)
        self.pages.addWidget(self.chat)

        studio = QWidget()
        studio_layout = vertical(studio, (60, 80, 60, 40), 16)
        studio_layout.addStretch()
        studio_layout.addWidget(label("Estúdio", "headline"))
        studio_layout.addWidget(label("Um espaço para dar forma às suas ideias.", "silver"))
        studio_layout.addWidget(label("Em breve · assets, Blender e Godot. Integração MCP disponível em Configurações → MCP.", "muted", True))
        studio_layout.addStretch(2)
        self.pages.addWidget(studio)

        self.settings = SettingsPage(repository, data_dir, self.backend, self.audio, self.tools)
        self.pages.addWidget(self.settings)
        self.settings.model_panel.catalog_changed.connect(self.update_models)
        if self.settings.tool_settings:
            self.settings.tool_settings.policy_changed.connect(self.refresh_permissions_label)
        if self.settings.api_settings:
            self.settings.api_settings.kilo_models_changed.connect(self.refresh_chat_models)
            self.settings.api_settings.use_kilo_model_requested.connect(self.activate_kilo_model)
        self.refresh_permissions_label()

        if not demo:
            self.composer.model.clear()
            self.composer.model.addItem("Nenhum modelo disponível")
            self.composer.model.setToolTip("Escolha um modelo Local (GGUF) ou Kilo Gateway")
            self.composer.mode.clear()
            self.composer.mode.addItem("Chat")
            self.task_button.hide()
            self.composer.model.activated.connect(self.select_chat_model)
            self.backend.ready_changed.connect(self.backend_ready)
            self.backend.state.connect(self.backend_state)
            self.backend.resources.connect(lambda value: self.local_status.setToolTip(value))
            self.backend.process.finished.connect(self.load_pending_model)
            self.refresh_chat_models()
        else:
            self.composer.kilo_button.hide()

        self.controller.failed.connect(self.show_error)
        self.controller.activity.connect(self.footer.setText)
        self.tools.approval_requested.connect(self.review_tool)
        self.audio.state.connect(self.audio_state)
        self.audio.error.connect(self.audio_state)
        self.audio.text_ready.connect(self.insert_transcription)
        self.audio.recording_changed.connect(self.recording_changed)
        self.audio.levels.connect(self.composer.set_voice_levels)

        self.tasks = TaskPanel(repository)
        self.tasks.restore()
        self.tasks.hide()
        shell.addWidget(self.tasks)
        self.controller.chunk.connect(self.stream_chunk)
        self.controller.finished.connect(self.stream_finished)
        self.shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        self.shortcut.activated.connect(self.new_conversation)
        self.restore_composer()
        self.refresh_history()
        last = repository.preference("last_conversation")
        conversations = repository.list_conversations()
        if last and any(c[0] == last for c in conversations):
            self.open_conversation(last)
        elif conversations:
            self.open_conversation(conversations[0][0])
        else:
            self.show_welcome()
        self.navigate(0)

    def refresh_permissions_label(self):
        count = len(self.tools.available())
        if count == 0:
            self.permissions.setText("Ferramentas desativadas")
        elif self.repository.preference("tool_ask_changes", False):
            self.permissions.setText(f"{count} ferramentas · com revisão")
        else:
            self.permissions.setText(f"{count} ferramentas · autônomas")

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)
        self.update_tasks_visibility()

    def toggle_sidebar(self):
        self.collapsed = not self.collapsed
        self.sidebar.setFixedWidth(48 if self.collapsed else 196)
        for widget in (self.brand, self.search, self.history, self.history_title, self.local_status, self.permissions):
            widget.setVisible(not self.collapsed)
        for nav, text in zip(self.nav + [self.new_button], ["Chat", "Estúdio", "Configurações", "Nova conversa"]):
            nav.setText("" if self.collapsed else text)
        self.sidebar.layout().setContentsMargins(4 if self.collapsed else 12, 18, 4 if self.collapsed else 12, 16)

    def clear_messages(self):
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def show_welcome(self):
        self.clear_messages()
        self.messages_layout.addStretch(1)
        welcome = QWidget()
        layout = vertical(welcome, (12, 0, 12, 0), 14)
        layout.addWidget(label("O que vamos criar hoje?", "headline"))
        layout.addWidget(label("IA local (GGUF) + Kilo Gateway API com ferramentas autônomas e voz.", "silver"))
        layout.addSpacing(12)
        for title, prompt in [
            ("Criar um jogo da velha em HTML/CSS/JS  ↗", "Crie um jogo da velha completo em HTML com CSS e JavaScript embutidos e design moderno"),
            ("Explorar arquivos do computador  ↗", "Liste os arquivos na pasta Downloads"),
            ("Conhecer o GameNext  ↗", "Quais ferramentas você pode usar no meu computador?"),
        ]:
            layout.addWidget(button(title, lambda checked=False, p=prompt: self.fill_prompt(p)))
        self.messages_layout.addWidget(welcome)
        self.messages_layout.addStretch(2)

    def fill_prompt(self, prompt):
        self.composer.input.setPlainText(prompt)
        self.composer.input.setFocus()

    def refresh_history(self):
        self.history.clear()
        for cid, title in self.repository.list_conversations(self.search.text()):
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, cid)
            item.setToolTip(title + " · botão direito para renomear/excluir")
            self.history.addItem(item)
            if cid == self.current_id:
                item.setSelected(True)

    def new_conversation(self):
        self.pending_send = None
        self.controller.stop()
        self.current_id = None
        self.repository.set_preference("last_conversation", None)
        self.title.setText("Nova conversa")
        self.show_welcome()
        self.navigate(0)
        self.composer.input.clear()
        self.composer.clear_attachments()
        self.composer.input.setFocus()
        self.refresh_history()

    def open_conversation(self, cid):
        self.pending_send = None
        self.controller.stop()
        self.current_id = cid
        self.repository.set_preference("last_conversation", cid)
        self.clear_messages()
        title = next((title for id_, title in self.repository.list_conversations() if id_ == cid), "Conversa")
        self.title.setText(title)
        for message in self.repository.messages(cid):
            self.messages_layout.addWidget(MessageView(message, self.repository, demo=self.demo))
        self.messages_layout.addStretch()
        self.navigate(0)
        self.scroll_bottom()

    def _selected_chat_model(self) -> dict | None:
        data = self.composer.model.currentData()
        return data if isinstance(data, dict) else None

    def send(self):
        if self.audio.recording or self.audio.transcribing or self.audio.queue:
            self.footer.setText("Conclua a gravação ou transcrição antes de enviar.")
            return
        if self.controller.active:
            self.controller.stop()
            return
        prompt = self.composer.input.toPlainText().strip()
        attachments = self.composer.attachments.copy()
        if not prompt and not attachments:
            return

        selected = self._selected_chat_model() if not self.demo else None
        provider = selected.get("provider", "local") if selected else "local"
        model_id = selected.get("id", "") if selected else ""
        model_label = selected.get("label", "") if selected else ""

        if not self.demo and provider == "local":
            if self.backend and (not self.backend.ready or self.pending_model_path):
                if not model_id:
                    self.footer.setText("Selecione um modelo Local (GGUF) ou Kilo Gateway em Configurações.")
                    return
                self.pending_send = (self.current_id, prompt)
                if self.backend.process.state() == QProcess.ProcessState.NotRunning and not self.pending_model_path:
                    self.select_chat_model(self.composer.model.currentIndex())
                if self.pending_send:
                    self.footer.setText("Carregando modelo local. A mensagem será enviada automaticamente quando estiver pronto…")
                return

        prompt = prompt or "Analise os arquivos anexados."
        if not self.current_id:
            self.current_id = self.repository.create(prompt.replace('\n', ' ')[:45])
        tasks = self.composer.mode.currentText() == "Tarefas"
        self.controller.start(
            self.current_id,
            prompt,
            attachments,
            tasks,
            provider=provider,
            model_id=model_id,
            model_label=model_label,
        )
        self.repository.set_preference("last_conversation", self.current_id)
        self.clear_messages()
        for message in self.repository.messages(self.current_id):
            view = MessageView(message, self.repository, demo=self.demo)
            self.messages_layout.addWidget(view)
            self.streaming_view = view
        self.messages_layout.addStretch()
        self.title.setText(next(t for c, t in self.repository.list_conversations() if c == self.current_id))
        self.composer.input.clear()
        self.composer.clear_attachments()
        self.composer.busy(self.controller.active)
        if not self.controller.active:
            self.streaming_view.render_final()
        else:
            self.footer.setText(
                f"Enviando para Kilo Gateway ({model_label})…" if provider == "kilo" else "Processando mensagem localmente…"
            )
        self.refresh_history()
        if tasks:
            self.tasks.start(prompt)
            self.task_requested = True
            self.update_tasks_visibility()
        self.scroll_bottom()

    def stream_chunk(self, text):
        bar = self.scroll.verticalScrollBar()
        at_bottom = bar.maximum() - bar.value() < 65
        self.streaming_view.update_text(text)
        if at_bottom:
            self.scroll_bottom()

    def update_models(self, models):
        self.local_catalog = list(models)
        self.refresh_chat_models()

    def refresh_chat_models(self):
        if self.demo:
            return
        current_selection = self._selected_chat_model() or self.repository.preference("last_chat_model")
        kilo_all = load_kilo_models(self.repository)
        kilo_enabled_ids = load_enabled_kilo_ids(self.repository)
        kilo_by_id = {m.id: m for m in kilo_all}
        kilo_visible = [kilo_by_id[mid] for mid in kilo_enabled_ids if mid in kilo_by_id]

        self.composer.model.blockSignals(True)
        self.composer.model.clear()

        for model in self.local_catalog:
            self.composer.model.addItem(
                f"Local · {model['name']}",
                {"provider": "local", "id": model["path"], "label": model["name"]},
            )
        for km in kilo_visible:
            tag = " · Grátis" if km.is_free else ""
            self.composer.model.addItem(
                f"Kilo · {km.name or km.id}{tag}",
                {"provider": "kilo", "id": km.id, "label": km.name or km.id},
            )

        if self.composer.model.count() == 0:
            self.composer.model.addItem("Nenhum modelo disponível", None)
        else:
            target_idx = 0
            if isinstance(current_selection, dict):
                for idx in range(self.composer.model.count()):
                    data = self.composer.model.itemData(idx)
                    if (
                        isinstance(data, dict)
                        and data.get("provider") == current_selection.get("provider")
                        and data.get("id") == current_selection.get("id")
                    ):
                        target_idx = idx
                        break
            elif self.backend and self.backend.ready:
                for idx in range(self.composer.model.count()):
                    data = self.composer.model.itemData(idx)
                    if isinstance(data, dict) and data.get("provider") == "local" and data.get("id") == self.backend.model_path:
                        target_idx = idx
                        break
            self.composer.model.setCurrentIndex(target_idx)

        self.composer.model.blockSignals(False)
        self._update_active_status_labels()

    def _update_active_status_labels(self):
        selected = self._selected_chat_model()
        if selected and selected.get("provider") == "kilo":
            self.local_status.setText("Kilo · " + selected.get("label", selected.get("id", ""))[:22])
        elif self.backend and self.backend.ready:
            self.local_status.setText("Local · modelo pronto")
        else:
            self.local_status.setText("Local · modelo não carregado")

    def open_kilo_catalog(self):
        models = load_kilo_models(self.repository)
        if not models:
            self.navigate(2)
            self.settings.tabs.setCurrentIndex(5)  # Aba API
            self.footer.setText("Adicione sua chave da Kilo Gateway API em Configurações → API e clique em Buscar modelos.")
            return
        enabled = load_enabled_kilo_ids(self.repository)
        rate = float(self.repository.preference("kilo_usd_to_brl", DEFAULT_USD_TO_BRL) or DEFAULT_USD_TO_BRL)
        dialog = KiloCatalogDialog(models, enabled, rate, self)

        def on_updated(ids: list[str]):
            self.repository.set_preference("kilo_chat_models", ids)
            if self.settings.api_settings:
                self.settings.api_settings.sync_from_repository()
            self.refresh_chat_models()

        dialog.chat_models_updated.connect(on_updated)
        dialog.use_model_requested.connect(self.activate_kilo_model)
        dialog.exec()

    def activate_kilo_model(self, model_id: str):
        self.refresh_chat_models()
        for idx in range(self.composer.model.count()):
            data = self.composer.model.itemData(idx)
            if isinstance(data, dict) and data.get("provider") == "kilo" and data.get("id") == model_id:
                self.composer.model.setCurrentIndex(idx)
                self.repository.set_preference("last_chat_model", data)
                self.footer.setText("Kilo Gateway pronto · " + data.get("label", model_id))
                self._update_active_status_labels()
                self.navigate(0)
                self.composer.input.setFocus()
                break

    def select_chat_model(self, index):
        data = self.composer.model.itemData(index)
        if not isinstance(data, dict):
            return
        if self.controller.active:
            self.footer.setText("Conclua ou pare a resposta antes de trocar de modelo.")
            return
        self.repository.set_preference("last_chat_model", data)
        if data.get("provider") == "kilo":
            self.pending_model_path = None
            self.pending_send = None
            self.footer.setText("Kilo Gateway pronto · " + data.get("label", data.get("id", "")))
            self._update_active_status_labels()
            return

        path = data.get("id", "")
        if not path:
            return
        panel = self.settings.model_panel
        panel.models.setCurrentIndex(panel.models.findData(path))
        if self.backend and self.backend.ready and self.backend.model_path == path:
            self.footer.setText("Modelo local pronto · " + Path(path).name)
            self._update_active_status_labels()
            return
        self.pending_model_path = path
        if self.backend.process.state() != QProcess.ProcessState.NotRunning:
            self.backend.unload()
        else:
            self.load_pending_model()

    def load_pending_model(self, *args):
        if not self.pending_model_path:
            return
        path, self.pending_model_path = self.pending_model_path, None
        panel = self.settings.model_panel
        panel.models.setCurrentIndex(panel.models.findData(path))
        self.footer.setText("Carregando " + Path(path).name + "…")
        if not panel.load():
            self.pending_send = None
            self.show_error(panel.status.text())

    def backend_ready(self, ready):
        self._update_active_status_labels()
        if ready:
            self.footer.setText("Modelo local pronto · " + self.backend.gpu_summary)
            for idx in range(self.composer.model.count()):
                data = self.composer.model.itemData(idx)
                if isinstance(data, dict) and data.get("provider") == "local" and data.get("id") == self.backend.model_path:
                    self.composer.model.blockSignals(True)
                    self.composer.model.setCurrentIndex(idx)
                    self.composer.model.blockSignals(False)
                    break
            pending, self.pending_send = self.pending_send, None
            if pending == (self.current_id, self.composer.input.toPlainText().strip()) and self.pages.currentWidget() == self.chat:
                self.send()

    def backend_state(self, state):
        self.footer.setText(state)

    def show_error(self, error):
        self.pending_send = None
        summary = " ".join(error.splitlines())
        self.footer.setText(summary[:200])
        self.footer.setToolTip(error)

    def microphone_action(self):
        if self.audio.recording:
            self.audio.stop_recording()
            return
        if self.repository.preference("microphone_id", ""):
            self.audio.start_recording(self.audio.selected_input())
            return
        dialog = MicrophoneDialog(self.audio, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.devices.currentData()
            device = next((d for d in self.audio.inputs() if bytes(d.id()).hex() == selected), self.audio.selected_input())
            self.audio.start_recording(device)

    def review_tool(self, request):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Revisar ação · GameNext")
        dialog.setText("Permitir esta ação da IA?")
        dialog.setInformativeText(request["tool"] + "\n" + json.dumps(request["arguments"], ensure_ascii=False, indent=2)[:4000])
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        self.tools.approve(dialog.exec() == QMessageBox.StandardButton.Yes)

    def recording_changed(self, recording):
        self.composer.set_voice_recording(recording)
        self.composer.microphone.setToolTip("Desligar ditado" if recording else "Ligar ditado contínuo")
        self.composer.input.setPlaceholderText("Ouvindo… fale normalmente" if recording else "Envie uma mensagem…")

    def audio_state(self, state):
        self.footer.setText(state)

    def insert_transcription(self, text):
        current = self.composer.input.toPlainText()
        self.composer.input.setPlainText((current + " " + text).strip())
        self.composer.input.setFocus()

    def stream_finished(self):
        self.composer.busy(False)
        if self.streaming_view:
            self.streaming_view.message = self.controller.message
            self.streaming_view.render_final()
            if self.controller.message.status == "concluído":
                src = "Kilo Gateway" if self.controller.message.provider == "kilo" else "inferência local"
                self.footer.setText(f"Concluído · {src}")

    def scroll_bottom(self):
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def toggle_tasks(self):
        self.task_requested = not self.task_requested
        self.update_tasks_visibility()

    def update_tasks_visibility(self):
        self.tasks.setVisible(self.task_requested and self.width() >= 1180 and self.pages.currentIndex() == 0)
        self.task_button.setToolTip("Painel disponível a partir de 1180 px" if self.width() < 1180 else "Mostrar ou ocultar tarefas")
        QTimer.singleShot(0, self.fit_composer)

    def fit_composer(self):
        self.composer.setFixedWidth(min(880, max(480, self.chat.width() - 56)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "tasks"):
            self.update_tasks_visibility()

    def save_composer(self):
        self.repository.set_preference(
            "composer",
            [self.composer.model.currentIndex(), self.composer.reasoning.currentIndex(), self.composer.mode.currentIndex()],
        )
        self.repository.set_preference("reasoning", self.composer.reasoning.currentText())
        selected = self._selected_chat_model()
        if selected:
            self.repository.set_preference("last_chat_model", selected)

    def restore_composer(self):
        indexes = self.repository.preference("composer", [0, 3, 0])
        for widget, index in zip((self.composer.model, self.composer.reasoning, self.composer.mode), indexes):
            widget.blockSignals(True)
            if widget.count() > 0:
                widget.setCurrentIndex(max(0, min(int(index), widget.count() - 1)))
            widget.blockSignals(False)

    def history_menu(self, pos):
        item = self.history.itemAt(pos)
        if not item:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        rename = menu.addAction("Renomear")
        delete = menu.addAction("Excluir")
        choice = menu.exec(self.history.mapToGlobal(pos))
        if choice == rename:
            title, ok = QInputDialog.getText(self, "Renomear conversa", "Nome", text=item.text())
            if ok and title.strip():
                self.repository.rename(cid, title.strip()[:100])
                if cid == self.current_id:
                    self.title.setText(title.strip()[:100])
        elif choice == delete:
            if QMessageBox.question(
                self, "Excluir conversa", "Excluir esta conversa e suas mensagens?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                if cid == self.current_id:
                    self.new_conversation()
                self.repository.delete(cid)
        self.refresh_history()

    def export(self):
        if not self.current_id:
            return
        path, selected = QFileDialog.getSaveFileName(self, "Exportar conversa", "conversa.md", "Markdown (*.md);;JSON (*.json)")
        if not path:
            return
        messages = self.repository.messages(self.current_id)
        try:
            if selected.startswith("JSON") or path.endswith(".json"):
                text = json.dumps([m.serialize() for m in messages], ensure_ascii=False, indent=2)
            else:
                text = "# " + self.title.text() + "\n\n" + "\n\n".join(
                    f"## {m.role}\n\n{m.content}"
                    + ("\n\nAnexos (referências locais):\n" + "\n".join(m.attachments) if m.attachments else "")
                    for m in messages
                )
            Path(path).write_text(text, encoding="utf-8")
            self.title.setToolTip("Conversa exportada: " + path)
        except OSError as error:
            self.title.setText("Não foi possível exportar. Verifique a pasta de destino.")
            import logging
            logging.getLogger(__name__).warning("Export failed: %s", error)

    def closeEvent(self, event):
        self.pending_send = None
        self.pending_model_path = None
        self.audio.shutdown()
        self.tools.shutdown()
        self.controller.stop()
        self.tasks.timer.stop()
        self.settings.model_panel.shutdown()
        if self.backend:
            self.backend.shutdown()
        if self.kilo_backend:
            self.kilo_backend.cancel()
        self.save_composer()
        self.repository.close()
        event.accept()
