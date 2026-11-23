"""Popups de detalhes completos de modelo Kilo Gateway e catálogo rápido para o chat."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
from gamenext.infrastructure.kilo_api import (
    DEFAULT_USD_TO_BRL,
    KiloModelInfo,
    format_brl_per_million,
    format_usd_per_million,
)
from gamenext.presentation.components import button, label, vertical
from gamenext.presentation.containers import container


CAP_SHORT_LABELS = {
    "code": "Código",
    "image": "Imagem",
    "video": "Vídeo",
    "audio": "Áudio",
    "file": "PDF/Arquivos",
    "reasoning": "Raciocínio",
    "text": "Texto",
}


class KiloModelDetailDialog(QDialog):
    """Popup modal exibindo todos os detalhes de um modelo da Kilo Gateway API."""

    chat_visibility_changed = pyqtSignal(str, bool)
    use_in_chat_requested = pyqtSignal(str)

    def __init__(
        self,
        model: KiloModelInfo,
        usd_to_brl: float,
        in_chat: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.model = model
        self.usd_to_brl = float(usd_to_brl or DEFAULT_USD_TO_BRL)
        self.setWindowTitle(f"Detalhes do modelo · {model.name or model.id}")
        self.setMinimumSize(620, 540)
        self.resize(680, 620)

        root = vertical(self, (20, 20, 20, 18), 14)

        # Header
        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        title_wrap = QWidget()
        title_wrap.setStyleSheet("background: transparent;")
        title_box = vertical(title_wrap, spacing=4)
        title_box.addWidget(label(model.name or model.id, "sectionTitle", True))
        id_row = QHBoxLayout()
        id_row.setSpacing(8)
        id_lbl = label(model.id, "muted", True)
        id_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        id_row.addWidget(id_lbl, 1)
        copy_btn = button("Copiar ID", lambda: QApplication.clipboard().setText(model.id))
        id_row.addWidget(copy_btn)
        title_box.addLayout(id_row)
        header_row.addWidget(title_wrap, 1)
        root.addLayout(header_row)

        # Badges strip
        badges = QHBoxLayout()
        badges.setSpacing(8)
        badges.addWidget(label(f"Nível: {model.power_tier}", "statusBadge"))
        badges.addWidget(label("Gratuito" if model.is_free else "Pago por uso", "statusBadge"))
        badges.addWidget(label(f"Contexto: {model.context_length:,} tokens".replace(",", "."), "statusBadge"))
        badges.addStretch()
        root.addLayout(badges)

        # Scrollable details body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_layout = vertical(body, (0, 2, 6, 4), 12)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        if model.description:
            desc_card = container()
            desc_box = vertical(desc_card, (16, 14, 16, 14), 6)
            desc_box.addWidget(label("Descrição", "fieldLabel"))
            desc_lbl = label(model.description, "silver", True)
            desc_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            desc_box.addWidget(desc_lbl)
            body_layout.addWidget(desc_card)

        # Pricing card
        price_card = container()
        price_box = vertical(price_card, (16, 14, 16, 14), 10)
        price_box.addWidget(label("Custos estimados (por 1 milhão de tokens)", "fieldLabel"))
        price_grid = QGridLayout()
        price_grid.setHorizontalSpacing(14)
        price_grid.setVerticalSpacing(10)

        def _price_pair(usd_val: float | None, fallback: str = "") -> str:
            if usd_val is None:
                return fallback or "Dinâmico (auto-roteador)"
            return f"{format_brl_per_million(usd_val, self.usd_to_brl)}  ({format_usd_per_million(usd_val)})"

        price_items = [
            ("Entrada (Prompt)", _price_pair(model.input_usd_per_m)),
            ("Saída (Resposta)", _price_pair(model.output_usd_per_m)),
            (
                "Cache (Leitura)",
                _price_pair(model.cache_read_usd_per_m, "Igual ao preço de entrada")
                if model.cache_read_usd_per_m is not None
                else "Igual ao preço de entrada",
            ),
            (
                "Cache (Escrita)",
                _price_pair(model.cache_write_usd_per_m, "Igual ao preço de entrada")
                if model.cache_write_usd_per_m is not None
                else "Igual ao preço de entrada",
            ),
        ]
        for idx, (k, v) in enumerate(price_items):
            cell = container("infoBanner")
            cbox = vertical(cell, (12, 9, 12, 9), 3)
            cbox.addWidget(label(k, "muted"))
            cbox.addWidget(label(v, "fieldLabel", True))
            price_grid.addWidget(cell, idx // 2, idx % 2)
        price_grid.setColumnStretch(0, 1)
        price_grid.setColumnStretch(1, 1)
        price_box.addLayout(price_grid)
        rate_str = f"{self.usd_to_brl:.2f}".replace(".", ",")
        extra_req = (
            f" · Taxa fixa por requisição: US$ {model.request_usd:.4f}".replace(".", ",")
            if model.request_usd > 0
            else ""
        )
        price_box.addWidget(label(f"Cotação aplicada: 1 USD = R$ {rate_str}{extra_req}", "muted", True))
        body_layout.addWidget(price_card)

        # Capabilities & modalities card
        cap_card = container()
        cap_box = vertical(cap_card, (16, 14, 16, 14), 10)
        cap_box.addWidget(label("Capacidades e modalidades", "fieldLabel"))
        cap_grid = QGridLayout()
        cap_grid.setHorizontalSpacing(14)
        cap_grid.setVerticalSpacing(10)
        cap_entries = [
            ("Modalidades de entrada", ", ".join(model.input_modalities) or "text"),
            ("Modalidades de saída", ", ".join(model.output_modalities) or "text"),
            ("Ferramentas (Tool Calling)", "Suportado" if model.supports_tools else "Não informado"),
            ("Raciocínio avançado", "Suportado" if model.supports_reasoning else "Padrão"),
            ("Visão (Imagens anexadas)", "Suportado" if model.supports_image_input else "Somente texto"),
            ("Arquivos / PDF", "Suportado nativamente" if model.supports_pdf_input else "Via extração local"),
        ]
        for idx, (k, v) in enumerate(cap_entries):
            cell = container("infoBanner")
            cbox = vertical(cell, (12, 9, 12, 9), 3)
            cbox.addWidget(label(k, "muted"))
            cbox.addWidget(label(v, "fieldLabel", True))
            cap_grid.addWidget(cell, idx // 2, idx % 2)
        cap_grid.setColumnStretch(0, 1)
        cap_grid.setColumnStretch(1, 1)
        cap_box.addLayout(cap_grid)

        cap_labels = " · ".join(c.label for c in model.capabilities)
        cap_box.addWidget(label("Recursos detectados: " + cap_labels, "silver", True))
        if model.supported_parameters:
            cap_box.addWidget(
                label("Parâmetros suportados: " + ", ".join(model.supported_parameters), "muted", True)
            )
        body_layout.addWidget(cap_card)

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # Footer controls
        footer = container("settingsFooter")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(14, 10, 14, 10)
        f_layout.setSpacing(10)

        self.show_in_chat = QCheckBox("Mostrar este modelo no Chat")
        self.show_in_chat.setChecked(in_chat)
        self.show_in_chat.toggled.connect(lambda checked: self.chat_visibility_changed.emit(self.model.id, checked))
        f_layout.addWidget(self.show_in_chat, 1)

        use_btn = button("Usar agora no Chat", self._use_now)
        use_btn.setObjectName("primaryControl")
        f_layout.addWidget(use_btn)
        f_layout.addWidget(button("Fechar", self.accept))
        root.addWidget(footer)

    def _use_now(self):
        if not self.show_in_chat.isChecked():
            self.show_in_chat.setChecked(True)
        self.use_in_chat_requested.emit(self.model.id)
        self.accept()


class KiloCatalogDialog(QDialog):
    """Popup rápido de catálogo Kilo Gateway acessível direto do Chat."""

    chat_models_updated = pyqtSignal(list)
    use_model_requested = pyqtSignal(str)

    def __init__(
        self,
        models: list[KiloModelInfo],
        enabled_ids: list[str],
        usd_to_brl: float,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.models = list(models)
        self.enabled_set = set(enabled_ids)
        self.usd_to_brl = float(usd_to_brl or DEFAULT_USD_TO_BRL)
        self.tier_filter = "Todos"
        self.only_free = False
        self._populating = False

        self.setWindowTitle("Modelos Kilo Gateway · GameNext")
        self.setMinimumSize(780, 560)
        self.resize(860, 620)

        root = vertical(self, (20, 18, 20, 16), 12)
        root.addWidget(label("Catálogo de modelos Kilo Gateway", "sectionTitle"))
        self.subtitle = label("", "silver")
        root.addWidget(self.subtitle)

        # Filters
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrar modelos por nome ou ID…")
        self.search.textChanged.connect(self.refresh_list)
        filter_row.addWidget(self.search, 1)

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
        root.addLayout(filter_row)

        # Models tree
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setHeaderLabels(["No chat · Modelo", "Nível", "Entrada / Saída (1M)", "Contexto", "Capacidades"])
        self.tree.setColumnWidth(0, 310)
        self.tree.setColumnWidth(1, 80)
        self.tree.setColumnWidth(2, 180)
        self.tree.setColumnWidth(3, 95)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemClicked.connect(self._on_item_clicked)
        root.addWidget(self.tree, 1)

        footer = QHBoxLayout()
        footer.addWidget(label("Marque a caixa para exibir no seletor do chat · clique no modelo para ver todos os detalhes.", "muted", True), 1)
        footer.addWidget(button("Fechar", self.accept))
        root.addLayout(footer)

        self.refresh_list()

    def _set_tier(self, tier: str):
        self.tier_filter = tier
        for name, btn in self.tier_buttons.items():
            btn.setChecked(name == tier)
        self.refresh_list()

    def _toggle_free(self):
        self.only_free = self.free_btn.isChecked()
        self.refresh_list()

    def refresh_list(self):
        term = self.search.text().strip().casefold()
        visible = [
            m for m in self.models
            if (not self.only_free or m.is_free)
            and (self.tier_filter == "Todos" or m.power_tier == self.tier_filter)
            and (not term or term in m.id.casefold() or term in m.name.casefold())
        ]
        rate_str = f"{self.usd_to_brl:.2f}".replace(".", ",")
        self.subtitle.setText(
            f"{len(visible)} de {len(self.models)} modelo(s) · {len(self.enabled_set)} selecionado(s) no chat · 1 USD = R$ {rate_str}"
        )
        self._populating = True
        self.tree.clear()
        for m in visible:
            if m.is_free:
                price_txt = "Grátis"
            elif m.input_usd_per_m is None or m.output_usd_per_m is None:
                price_txt = "Dinâmico"
            else:
                price_txt = f"{format_brl_per_million(m.input_usd_per_m, self.usd_to_brl)} / {format_brl_per_million(m.output_usd_per_m, self.usd_to_brl)}"
            ctx_txt = f"{m.context_length // 1000}k" if m.context_length >= 1000 else str(m.context_length)
            caps_txt = " · ".join(CAP_SHORT_LABELS.get(c.key, c.label) for c in m.capabilities[:4])
            item = QTreeWidgetItem([m.name or m.id, m.power_tier, price_txt, ctx_txt, caps_txt])
            item.setData(0, Qt.ItemDataRole.UserRole, m.id)
            item.setToolTip(0, m.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if m.id in self.enabled_set else Qt.CheckState.Unchecked)
            self.tree.addTopLevelItem(item)
        self._populating = False

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if self._populating or column != 0:
            return
        model_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not model_id:
            return
        if item.checkState(0) == Qt.CheckState.Checked:
            self.enabled_set.add(model_id)
        else:
            self.enabled_set.discard(model_id)
        ordered = [m.id for m in self.models if m.id in self.enabled_set]
        self.chat_models_updated.emit(ordered)
        rate_str = f"{self.usd_to_brl:.2f}".replace(".", ",")
        self.subtitle.setText(
            f"{self.tree.topLevelItemCount()} de {len(self.models)} modelo(s) · {len(self.enabled_set)} selecionado(s) no chat · 1 USD = R$ {rate_str}"
        )

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        # Clicking columns 1..4 opens details immediately; clicking column 0 text (not checkbox) also opens details.
        model_id = item.data(0, Qt.ItemDataRole.UserRole)
        model = next((m for m in self.models if m.id == model_id), None)
        if not model:
            return
        if column == 0:
            # Avoid opening popup when the user clicked specifically on the checkbox rect on the far left.
            pos = self.tree.viewport().mapFromGlobal(self.cursor().pos())
            rect = self.tree.visualItemRect(item)
            if pos.x() - rect.x() <= 28:
                return
        dialog = KiloModelDetailDialog(model, self.usd_to_brl, model.id in self.enabled_set, self)

        def on_vis(mid: str, checked: bool):
            if checked:
                self.enabled_set.add(mid)
            else:
                self.enabled_set.discard(mid)
            ordered = [m.id for m in self.models if m.id in self.enabled_set]
            self.chat_models_updated.emit(ordered)
            self.refresh_list()

        def on_use(mid: str):
            self.enabled_set.add(mid)
            ordered = [m.id for m in self.models if m.id in self.enabled_set]
            self.chat_models_updated.emit(ordered)
            self.use_model_requested.emit(mid)
            self.accept()

        dialog.chat_visibility_changed.connect(on_vis)
        dialog.use_in_chat_requested.connect(on_use)
        dialog.exec()
