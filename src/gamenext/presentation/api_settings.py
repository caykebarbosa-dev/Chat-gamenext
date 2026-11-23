"""Configurações de API: Kilo Gateway (com catálogo interativo e popup), Groq Voz e Perfis HTTP."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
from gamenext.infrastructure.groq_api import (
    DEFAULT_GROQ_STT_MODEL,
    GROQ_STT_MODELS,
    resolve_groq_api_key,
    save_groq_api_key,
    validate_groq_connection,
)
from gamenext.infrastructure.kilo_api import (
    DEFAULT_USD_TO_BRL,
    KiloModelInfo,
    fetch_kilo_catalog,
    format_brl_per_million,
    load_enabled_kilo_ids,
    load_kilo_models,
    resolve_kilo_api_key,
    save_kilo_api_key,
    save_kilo_catalog,
)
from gamenext.presentation.components import button, label, vertical
from gamenext.presentation.containers import container, field_block
from gamenext.presentation.kilo_model_dialog import CAP_SHORT_LABELS, KiloModelDetailDialog
from gamenext.presentation.tool_settings import ConnectionSettings


class _KiloFetchThread(QThread):
    loaded = pyqtSignal(list, float)
    failed = pyqtSignal(str)

    def __init__(self, api_key: str, parent=None):
        super().__init__(parent)
        self.api_key = api_key

    def run(self):
        try:
            models, rate = fetch_kilo_catalog(self.api_key)
            self.loaded.emit(models, rate)
        except Exception as error:
            self.failed.emit(str(error))


class _GroqValidateThread(QThread):
    validated = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, api_key: str, parent=None):
        super().__init__(parent)
        self.api_key = api_key

    def run(self):
        try:
            models = validate_groq_connection(self.api_key)
            self.validated.emit(models)
        except Exception as error:
            self.failed.emit(str(error))


class ApiSettings(QWidget):
    """Aba Configurações → API com Kilo Gateway, Groq API e perfis HTTP personalizados."""

    kilo_models_changed = pyqtSignal()
    use_kilo_model_requested = pyqtSignal(str)
    voice_provider_changed = pyqtSignal(str)

    def __init__(self, repository, tool_controller):
        super().__init__()
        self.repository = repository
        self.tool_controller = tool_controller
        self._kilo_thread: _KiloFetchThread | None = None
        self._groq_thread: _GroqValidateThread | None = None
        self._populating_kilo = False

        self.kilo_models: list[KiloModelInfo] = load_kilo_models(repository)
        self.enabled_kilo_ids: set[str] = set(load_enabled_kilo_ids(repository))
        self.usd_to_brl: float = float(repository.preference("kilo_usd_to_brl", DEFAULT_USD_TO_BRL) or DEFAULT_USD_TO_BRL)
        self.tier_filter = "Todos"
        self.only_free = False

        outer = vertical(self, spacing=14)
        self._build_kilo_card(outer)
        self._build_groq_card(outer)
        self._build_custom_http_section(outer)

    # ── Kilo Gateway API ────────────────────────────────────────────────────
    def _build_kilo_card(self, outer):
        card = container()
        box = vertical(card, (18, 16, 18, 16), 12)

        top = QHBoxLayout()
        top.addWidget(label("Kilo Gateway API (kilo.ai)", "sectionTitle"), 1)
        self.kilo_badge = label("", "statusBadge")
        top.addWidget(self.kilo_badge)
        box.addLayout(top)

        box.addWidget(label(
            "Adicione sua chave da API de kilo.ai para listar todos os modelos disponíveis. "
            "Marque os modelos que deseja exibir no chat e clique em qualquer modelo para abrir o popup com todos os detalhes.",
            "silver",
            True,
        ))

        has_key = bool(resolve_kilo_api_key(self.repository))
        self.kilo_key_input = QLineEdit()
        self.kilo_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.kilo_key_input.setPlaceholderText(
            "Chave ativa salva com segurança (cole outra apenas para substituir)"
            if has_key
            else "Cole sua chave da Kilo Gateway API (kilo.ai)"
        )

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_row.addWidget(self.kilo_key_input, 1)
        self.kilo_eye_btn = button("Mostrar", self._toggle_kilo_key_visibility)
        self.kilo_eye_btn.setCheckable(True)
        key_row.addWidget(self.kilo_eye_btn)
        self.kilo_fetch_btn = button("Buscar modelos", self.fetch_kilo_models)
        self.kilo_fetch_btn.setObjectName("primaryControl")
        key_row.addWidget(self.kilo_fetch_btn)
        key_row.addWidget(button("Remover chave", self.clear_kilo_key))
        box.addWidget(label("Chave da API (Kilo Gateway)", "fieldLabel"))
        box.addLayout(key_row)

        self.kilo_status = label("", "silver", True)
        box.addWidget(self.kilo_status)

        # Filter bar for models list
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.kilo_search = QLineEdit()
        self.kilo_search.setPlaceholderText("Filtrar modelos por nome ou ID…")
        self.kilo_search.textChanged.connect(self.refresh_kilo_table)
        filter_row.addWidget(self.kilo_search, 1)

        self.tier_buttons = {}
        for tier in ("Todos", "Básico", "Médio", "Max", "Ultra"):
            btn = button(tier, lambda checked=False, t=tier: self._set_tier(t))
            btn.setCheckable(True)
            btn.setChecked(tier == "Todos")
            self.tier_buttons[tier] = btn
            filter_row.addWidget(btn)

        self.free_btn = button("Grátis", self._toggle_free)
        self.free_btn.setCheckable(True)
        filter_row.addWidget(self.free_btn)
        box.addLayout(filter_row)

        # Models list directly below API config
        self.kilo_tree = QTreeWidget()
        self.kilo_tree.setRootIsDecorated(False)
        self.kilo_tree.setUniformRowHeights(True)
        self.kilo_tree.setMinimumHeight(260)
        self.kilo_tree.setMaximumHeight(360)
        self.kilo_tree.setHeaderLabels([
            "No chat · Modelo (clique para detalhes)",
            "Nível",
            "Entrada / Saída (1M)",
            "Contexto",
            "Capacidades",
        ])
        self.kilo_tree.setColumnWidth(0, 320)
        self.kilo_tree.setColumnWidth(1, 78)
        self.kilo_tree.setColumnWidth(2, 175)
        self.kilo_tree.setColumnWidth(3, 86)
        self.kilo_tree.itemChanged.connect(self._on_kilo_item_changed)
        self.kilo_tree.itemClicked.connect(self._on_kilo_item_clicked)
        box.addWidget(self.kilo_tree)

        bulk_row = QHBoxLayout()
        bulk_row.setSpacing(8)
        bulk_row.addWidget(button("Marcar grátis no chat", self._select_free_models))
        bulk_row.addWidget(button("Limpar seleção do chat", self._clear_selected_models))
        bulk_row.addStretch()
        self.kilo_hint = label("Clique em um modelo acima para abrir o popup com todos os detalhes.", "muted")
        bulk_row.addWidget(self.kilo_hint)
        box.addLayout(bulk_row)

        outer.addWidget(card)
        self.refresh_kilo_table()

    def _toggle_kilo_key_visibility(self):
        visible = self.kilo_eye_btn.isChecked()
        self.kilo_key_input.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.kilo_eye_btn.setText("Ocultar" if visible else "Mostrar")

    def _set_tier(self, tier: str):
        self.tier_filter = tier
        for name, btn in self.tier_buttons.items():
            btn.setChecked(name == tier)
        self.refresh_kilo_table()

    def _toggle_free(self):
        self.only_free = self.free_btn.isChecked()
        self.refresh_kilo_table()

    def _update_kilo_badges(self, visible_count: int):
        total = len(self.kilo_models)
        selected = len(self.enabled_kilo_ids)
        if total:
            self.kilo_badge.setText(f"{total} modelos · {selected} no chat")
            rate_str = f"{self.usd_to_brl:.2f}".replace(".", ",")
            self.kilo_status.setText(
                f"Exibindo {visible_count} de {total} modelo(s) da Kilo Gateway · Cotação: 1 USD = R$ {rate_str}"
            )
        else:
            has_key = bool(resolve_kilo_api_key(self.repository))
            self.kilo_badge.setText("Chave salva" if has_key else "Aguardando chave")
            self.kilo_status.setText("Cole sua chave da Kilo Gateway API e clique em Buscar modelos.")

    def refresh_kilo_table(self):
        term = self.kilo_search.text().strip().casefold()
        visible = [
            m for m in self.kilo_models
            if (not self.only_free or m.is_free)
            and (self.tier_filter == "Todos" or m.power_tier == self.tier_filter)
            and (not term or term in m.id.casefold() or term in m.name.casefold())
        ]
        self._populating_kilo = True
        self.kilo_tree.clear()
        for m in visible:
            if m.is_free:
                price_txt = "Grátis"
            elif m.input_usd_per_m is None or m.output_usd_per_m is None:
                price_txt = "Dinâmico"
            else:
                price_txt = (
                    f"{format_brl_per_million(m.input_usd_per_m, self.usd_to_brl)} / "
                    f"{format_brl_per_million(m.output_usd_per_m, self.usd_to_brl)}"
                )
            ctx_txt = f"{m.context_length // 1000}k" if m.context_length >= 1000 else str(m.context_length)
            caps_txt = " · ".join(CAP_SHORT_LABELS.get(c.key, c.label) for c in m.capabilities[:4])
            item = QTreeWidgetItem([m.name or m.id, m.power_tier, price_txt, ctx_txt, caps_txt])
            item.setData(0, Qt.ItemDataRole.UserRole, m.id)
            item.setToolTip(0, f"{m.id} · clique para abrir detalhes completos")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if m.id in self.enabled_kilo_ids else Qt.CheckState.Unchecked)
            self.kilo_tree.addTopLevelItem(item)
        self._populating_kilo = False
        self._update_kilo_badges(len(visible))

    def _persist_kilo_selection(self):
        ordered = [m.id for m in self.kilo_models if m.id in self.enabled_kilo_ids]
        self.repository.set_preference("kilo_chat_models", ordered)
        self.kilo_models_changed.emit()

    def _on_kilo_item_changed(self, item: QTreeWidgetItem, column: int):
        if self._populating_kilo or column != 0:
            return
        model_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not model_id:
            return
        if item.checkState(0) == Qt.CheckState.Checked:
            self.enabled_kilo_ids.add(model_id)
        else:
            self.enabled_kilo_ids.discard(model_id)
        self._persist_kilo_selection()
        self._update_kilo_badges(self.kilo_tree.topLevelItemCount())

    def _on_kilo_item_clicked(self, item: QTreeWidgetItem, column: int):
        model_id = item.data(0, Qt.ItemDataRole.UserRole)
        model = next((m for m in self.kilo_models if m.id == model_id), None)
        if not model:
            return
        if column == 0:
            pos = self.kilo_tree.viewport().mapFromGlobal(self.cursor().pos())
            rect = self.kilo_tree.visualItemRect(item)
            if pos.x() - rect.x() <= 28:
                return
        self.open_model_details(model)

    def open_model_details(self, model: KiloModelInfo):
        dialog = KiloModelDetailDialog(model, self.usd_to_brl, model.id in self.enabled_kilo_ids, self)

        def on_vis(mid: str, checked: bool):
            if checked:
                self.enabled_kilo_ids.add(mid)
            else:
                self.enabled_kilo_ids.discard(mid)
            self._persist_kilo_selection()
            self.refresh_kilo_table()

        def on_use(mid: str):
            self.enabled_kilo_ids.add(mid)
            self._persist_kilo_selection()
            self.refresh_kilo_table()
            self.use_kilo_model_requested.emit(mid)

        dialog.chat_visibility_changed.connect(on_vis)
        dialog.use_in_chat_requested.connect(on_use)
        dialog.exec()

    def _select_free_models(self):
        for m in self.kilo_models:
            if m.is_free:
                self.enabled_kilo_ids.add(m.id)
        self._persist_kilo_selection()
        self.refresh_kilo_table()

    def _clear_selected_models(self):
        self.enabled_kilo_ids.clear()
        self._persist_kilo_selection()
        self.refresh_kilo_table()

    def fetch_kilo_models(self):
        if self._kilo_thread and self._kilo_thread.isRunning():
            return
        typed = self.kilo_key_input.text().strip()
        key = typed or resolve_kilo_api_key(self.repository)
        if not key:
            self.kilo_status.setText("Cole sua chave da Kilo Gateway API antes de buscar os modelos.")
            return
        self.kilo_fetch_btn.setEnabled(False)
        self.kilo_status.setText("Validando chave e carregando modelos da Kilo Gateway…")
        self._kilo_thread = _KiloFetchThread(key, self)

        def on_loaded(models: list[KiloModelInfo], rate: float):
            if typed:
                save_kilo_api_key(self.repository, typed)
                self.kilo_key_input.clear()
                self.kilo_key_input.setPlaceholderText("Chave ativa salva com segurança (cole outra apenas para substituir)")
            self.kilo_models = models
            self.usd_to_brl = rate
            enabled = save_kilo_catalog(self.repository, models, rate, None)
            self.enabled_kilo_ids = set(enabled)
            self.refresh_kilo_table()
            self.kilo_models_changed.emit()
            self.kilo_fetch_btn.setEnabled(True)

        def on_failed(message: str):
            self.kilo_status.setText(message)
            self.kilo_fetch_btn.setEnabled(True)

        self._kilo_thread.loaded.connect(on_loaded)
        self._kilo_thread.failed.connect(on_failed)
        self._kilo_thread.start()

    def clear_kilo_key(self):
        save_kilo_api_key(self.repository, "")
        self.kilo_key_input.clear()
        self.kilo_key_input.setPlaceholderText("Cole sua chave da Kilo Gateway API (kilo.ai)")
        self.kilo_models = []
        self.enabled_kilo_ids.clear()
        self.repository.set_preference("kilo_models", [])
        self.repository.set_preference("kilo_chat_models", [])
        self.refresh_kilo_table()
        self.kilo_models_changed.emit()

    def sync_from_repository(self):
        self.kilo_models = load_kilo_models(self.repository)
        self.enabled_kilo_ids = set(load_enabled_kilo_ids(self.repository))
        self.usd_to_brl = float(self.repository.preference("kilo_usd_to_brl", DEFAULT_USD_TO_BRL) or DEFAULT_USD_TO_BRL)
        self.refresh_kilo_table()

    # ── Groq API (Voz no Chat) ──────────────────────────────────────────────
    def _build_groq_card(self, outer):
        card = container()
        box = vertical(card, (18, 16, 18, 16), 12)

        top = QHBoxLayout()
        top.addWidget(label("Groq API · Fala para texto no Chat", "sectionTitle"), 1)
        self.groq_badge = label("", "statusBadge")
        top.addWidget(self.groq_badge)
        box.addLayout(top)

        box.addWidget(label(
            "Transcrição ultrarrápida do microfone via console.groq.com. "
            "Alterne livremente entre Whisper local (offline) e Groq API.",
            "silver",
            True,
        ))

        prov_row = QHBoxLayout()
        prov_row.setSpacing(8)
        self.btn_whisper = button("Whisper (Local)", lambda: self._set_voice_provider("whisper"))
        self.btn_whisper.setCheckable(True)
        self.btn_groq = button("Groq API", lambda: self._set_voice_provider("groq"))
        self.btn_groq.setCheckable(True)
        prov_row.addWidget(self.btn_whisper)
        prov_row.addWidget(self.btn_groq)
        prov_row.addStretch()
        box.addWidget(label("Motor de voz do microfone", "fieldLabel"))
        box.addLayout(prov_row)

        has_groq_key = bool(resolve_groq_api_key(self.repository))
        self.groq_key_input = QLineEdit()
        self.groq_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.groq_key_input.setPlaceholderText(
            "Chave ativa salva com segurança (cole outra apenas para substituir)"
            if has_groq_key
            else "Cole sua chave da Groq API (console.groq.com)"
        )
        groq_key_row = QHBoxLayout()
        groq_key_row.setSpacing(8)
        groq_key_row.addWidget(self.groq_key_input, 1)
        self.groq_eye_btn = button("Mostrar", self._toggle_groq_key_visibility)
        self.groq_eye_btn.setCheckable(True)
        groq_key_row.addWidget(self.groq_eye_btn)
        box.addWidget(label("Chave da API (Groq)", "fieldLabel"))
        box.addLayout(groq_key_row)

        self.groq_model_combo = QComboBox()
        self._populate_groq_models()
        self.groq_model_combo.currentIndexChanged.connect(self._save_groq_model)
        box.addWidget(field_block("Modelo de fala Groq", self.groq_model_combo))

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.groq_save_btn = button("Validar e salvar Groq", self.validate_groq)
        self.groq_save_btn.setObjectName("primaryControl")
        actions.addWidget(self.groq_save_btn)
        actions.addWidget(button("Remover chave Groq", self.clear_groq_key))
        actions.addStretch()
        box.addLayout(actions)

        self.groq_status = label("", "silver", True)
        box.addWidget(self.groq_status)

        outer.addWidget(card)
        self._refresh_groq_ui()

    def _populate_groq_models(self):
        validated = self.repository.preference("groq_validated_models", [])
        if not isinstance(validated, list):
            validated = []
        labels = {
            "whisper-large-v3-turbo": "whisper-large-v3-turbo (Rápido)",
            "whisper-large-v3": "whisper-large-v3 (Preciso)",
        }
        ordered = list(GROQ_STT_MODELS)
        for m in validated:
            if isinstance(m, str) and m and m not in ordered:
                ordered.append(m)
        saved_model = str(self.repository.preference("groq_model", DEFAULT_GROQ_STT_MODEL) or DEFAULT_GROQ_STT_MODEL)
        self.groq_model_combo.blockSignals(True)
        self.groq_model_combo.clear()
        for mid in ordered:
            self.groq_model_combo.addItem(labels.get(mid, mid), mid)
        idx = self.groq_model_combo.findData(saved_model)
        self.groq_model_combo.setCurrentIndex(max(0, idx))
        self.groq_model_combo.blockSignals(False)

    def _toggle_groq_key_visibility(self):
        visible = self.groq_eye_btn.isChecked()
        self.groq_key_input.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.groq_eye_btn.setText("Ocultar" if visible else "Mostrar")

    def _set_voice_provider(self, provider: str):
        chosen = "groq" if provider == "groq" else "whisper"
        self.repository.set_preference("voice_provider", chosen)
        self._refresh_groq_ui()
        self.voice_provider_changed.emit(chosen)
        if chosen == "groq" and not resolve_groq_api_key(self.repository):
            self.groq_status.setText("Cole e valide sua chave da Groq API para transcrever voz pela Groq.")
        elif chosen == "groq":
            self.groq_status.setText("Microfone configurado para transcrever com Groq API.")
        else:
            self.groq_status.setText("Microfone configurado para Whisper local (offline).")

    def _save_groq_model(self):
        model = self.groq_model_combo.currentData()
        if model:
            self.repository.set_preference("groq_model", model)

    def _refresh_groq_ui(self):
        provider = self.repository.preference("voice_provider", "whisper")
        has_key = bool(resolve_groq_api_key(self.repository))
        self.btn_whisper.setChecked(provider != "groq")
        self.btn_groq.setChecked(provider == "groq")
        if has_key and provider == "groq":
            self.groq_badge.setText("Groq ativo")
        elif has_key:
            self.groq_badge.setText("Whisper local (Groq pronta)")
        else:
            self.groq_badge.setText("Whisper local")

    def validate_groq(self):
        if self._groq_thread and self._groq_thread.isRunning():
            return
        typed = self.groq_key_input.text().strip()
        key = typed or resolve_groq_api_key(self.repository)
        if not key:
            self.groq_status.setText("Cole sua chave da Groq API primeiro.")
            return
        self.groq_save_btn.setEnabled(False)
        self.groq_status.setText("Validando chave na Groq API…")
        self._groq_thread = _GroqValidateThread(key, self)

        def on_ok(models: list[str]):
            if typed:
                save_groq_api_key(self.repository, typed)
                self.groq_key_input.clear()
                self.groq_key_input.setPlaceholderText("Chave ativa salva com segurança (cole outra apenas para substituir)")
            self.repository.set_preference("groq_validated_models", models)
            self.repository.set_preference("voice_provider", "groq")
            self._populate_groq_models()
            self._refresh_groq_ui()
            self.voice_provider_changed.emit("groq")
            self.groq_status.setText(f"Groq API validada ({len(models)} modelo(s) Whisper). Provedor de voz definido para Groq API.")
            self.groq_save_btn.setEnabled(True)

        def on_err(message: str):
            self.groq_status.setText(message)
            self.groq_save_btn.setEnabled(True)

        self._groq_thread.validated.connect(on_ok)
        self._groq_thread.failed.connect(on_err)
        self._groq_thread.start()

    def clear_groq_key(self):
        save_groq_api_key(self.repository, "")
        self.groq_key_input.clear()
        self.groq_key_input.setPlaceholderText("Cole sua chave da Groq API (console.groq.com)")
        self.repository.set_preference("voice_provider", "whisper")
        self._refresh_groq_ui()
        self.voice_provider_changed.emit("whisper")
        self.groq_status.setText("Chave Groq removida. Microfone retornou para Whisper local.")

    # ── Perfis API HTTP Personalizados ──────────────────────────────────────
    def _build_custom_http_section(self, outer):
        self.http_connections = ConnectionSettings(self.repository, self.tool_controller, "api")
        outer.addWidget(self.http_connections)
