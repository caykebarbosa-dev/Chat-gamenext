"""Refined, unrestricted settings experience with hardware presets and clear layout."""
import os
import psutil
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QCheckBox, QFileDialog, QScrollArea, QHBoxLayout, QGridLayout,
)
from gamenext.infrastructure.storage import default_cpu_threads, default_batch_threads
from gamenext.presentation.model_settings import ModelSettings
from gamenext.presentation.components import label, button, vertical
from gamenext.presentation.containers import container, field_block
from gamenext.presentation.audio_settings import AudioSettings
from gamenext.presentation.tool_settings import ToolSettings, ConnectionSettings
from gamenext.presentation.api_settings import ApiSettings


GPU_MODES = [
    ("auto", "Automático (GPU + RAM · --fit on)"),
    ("gpu_all", "Todas as camadas na GPU"),
    ("custom", "Camadas manuais na GPU"),
    ("cpu", "Apenas CPU"),
]

FLASH_MODES = [
    ("auto", "Automático"),
    ("on", "Ligado"),
    ("off", "Desligado"),
]

KV_MODES = [
    ("f16", "F16 (máxima precisão)"),
    ("q8_0", "Q8_0 (economiza VRAM)"),
    ("q4_0", "Q4_0 (economia máxima)"),
]


class SettingsPage(QWidget):
    def __init__(self, repository, data_dir, backend=None, audio_controller=None, tool_controller=None):
        super().__init__()
        self.setObjectName("settingsPage")
        self.repository = repository
        self.data_dir = data_dir
        self.controls = {}

        layout = vertical(self, (28, 22, 28, 18), 14)

        # Header
        header_box = QHBoxLayout()
        title_wrap = QWidget()
        title_col = vertical(title_wrap, spacing=3)
        title_col.addWidget(label("Configurações", "headline"))
        title_col.addWidget(label("Inferência local sem limitações artificiais · adaptado ao seu computador.", "silver"))
        header_box.addWidget(title_wrap, 1)
        layout.addLayout(header_box)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # Tab 0: Geral
        general = self.tab("Geral")
        self._build_general_tab(general)

        # Tab 1: Modelos
        models = self.tab("Modelos")
        self.model_panel = ModelSettings(repository, backend, self.performance_config)
        self.folder = self.model_panel.folder
        models.addWidget(self.model_panel)

        # Tab 2: Desempenho
        performance = self.tab("Desempenho")
        self._build_performance_tab(performance, backend)

        # Tab 3, 4, 5: Ferramentas, MCP, API
        tools = self.tab("Ferramentas")
        self.tool_settings = None
        self.api_settings = None
        if tool_controller:
            self.tool_settings = ToolSettings(repository, tool_controller)
            tools.addWidget(self.tool_settings)
            self.tab("MCP").addWidget(ConnectionSettings(repository, tool_controller, "mcp"))
            self.api_settings = ApiSettings(repository, tool_controller)
            self.tab("API").addWidget(self.api_settings)
        else:
            self.tab("MCP")
            self.tab("API")

        # Tab 6: Áudio
        audio = self.tab("Áudio")
        if audio_controller:
            audio.addWidget(AudioSettings(audio_controller))

        # Tab 7: Dados
        data = self.tab("Dados")
        self._build_data_tab(data, data_dir)

        # Connect hardware probe update to performance banner
        self.model_panel.hardware_changed.connect(self._update_hardware_banner)

        # Compact bottom action bar
        footer = container("settingsFooter")
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(16, 10, 16, 10)
        footer_row.setSpacing(12)
        self.notice = label("Alterações salvas localmente. Recarregue o modelo para aplicar novos parâmetros de inferência.", "silver", True)
        footer_row.addWidget(self.notice, 1)
        footer_row.addWidget(button("Restaurar padrões", self.defaults))
        apply_button = button("Aplicar preferências", self.save)
        apply_button.setObjectName("primaryControl")
        footer_row.addWidget(apply_button)
        layout.addWidget(footer)

    def tab(self, title: str):
        page = QWidget()
        box = vertical(page, (0, 10, 12, 16), 14)
        box.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, title)
        return box

    def _build_general_tab(self, parent_layout):
        card = container()
        box = vertical(card, (18, 16, 18, 16), 12)
        box.addWidget(label("Sobre o GameNext", "sectionTitle"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        entries = [
            ("Versão", "GameNext 0.4.0 · IA local, ferramentas autônomas e voz offline"),
            ("Motor de inferência", "llama.cpp nativo via Vulkan (GPU + híbrido GPU/RAM + CPU)"),
            ("Atalhos do teclado", "Ctrl+N: nova conversa · Enter: enviar · Shift+Enter: quebra de linha"),
            ("Privacidade", "100% local em 127.0.0.1 · sem telemetria e sem envio à nuvem"),
        ]
        for idx, (k, v) in enumerate(entries):
            item = container("infoBanner")
            inner = vertical(item, (14, 10, 14, 10), 4)
            inner.addWidget(label(k, "fieldLabel"))
            inner.addWidget(label(v, "silver", True))
            grid.addWidget(item, idx // 2, idx % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        box.addLayout(grid)
        parent_layout.addWidget(card)

    def _build_performance_tab(self, parent_layout, backend):
        # Card 1: Hardware summary + quick one-click profiles
        hw_card = container()
        hw_box = vertical(hw_card, (18, 16, 18, 16), 12)
        hw_box.addWidget(label("Hardware detectado e perfis rápidos", "sectionTitle"))
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        cpu_threads = os.cpu_count() or 4
        self.hw_summary = label(
            f"CPU: {cpu_threads} threads lógicas · RAM total: {ram_gb:.1f} GB · GPU: detectando Vulkan…",
            "statusBadge",
            True,
        )
        hw_box.addWidget(self.hw_summary)
        hw_box.addWidget(label("Aplique um perfil pronto ou ajuste manualmente qualquer valor abaixo sem restrições:", "silver", True))

        preset_row = QHBoxLayout()
        preset_row.setSpacing(10)
        for text, preset_name in [
            ("Otimizado para este PC (Sem limites)", "recommended"),
            ("Máxima velocidade GPU", "max_gpu"),
            ("Híbrido GPU + RAM (Modelos grandes)", "hybrid_large"),
        ]:
            btn = button(text, lambda checked=False, p=preset_name: self.apply_preset(p))
            btn.setObjectName("presetControl")
            preset_row.addWidget(btn)
        preset_row.addStretch()
        hw_box.addLayout(preset_row)
        parent_layout.addWidget(hw_card)

        # Card 2: GPU & Acceleration
        gpu_card = container()
        gpu_box = vertical(gpu_card, (18, 16, 18, 16), 12)
        gpu_box.addWidget(label("Aceleração e memória de vídeo", "sectionTitle"))
        gpu_grid = QGridLayout()
        gpu_grid.setHorizontalSpacing(16)
        gpu_grid.setVerticalSpacing(12)

        self.gpu_mode = QComboBox()
        for value, text in GPU_MODES:
            self.gpu_mode.addItem(text, value)
        saved_mode = self.repository.preference("gpu_mode", "auto")
        self.gpu_mode.setCurrentIndex(max(0, self.gpu_mode.findData(saved_mode)))
        self.gpu_mode.currentIndexChanged.connect(self._sync_gpu_layers_state)

        self.controls["gpu_layers"] = self._spin(0, 999, self.repository.preference("gpu_layers", 99), " camadas")
        self.flash_attn = QComboBox()
        for value, text in FLASH_MODES:
            self.flash_attn.addItem(text, value)
        self.flash_attn.setCurrentIndex(max(0, self.flash_attn.findData(self.repository.preference("flash_attn", "auto"))))

        self.kv_cache = QComboBox()
        for value, text in KV_MODES:
            self.kv_cache.addItem(text, value)
        self.kv_cache.setCurrentIndex(max(0, self.kv_cache.findData(self.repository.preference("kv_cache", "f16"))))

        gpu_grid.addWidget(field_block("Modo de execução GPU", self.gpu_mode, "Automático usa 100% GPU quando cabe e divide com RAM em modelos grandes."), 0, 0)
        gpu_grid.addWidget(field_block("Camadas manuais na GPU", self.controls["gpu_layers"], "Usado apenas quando o modo for 'Camadas manuais'."), 0, 1)
        gpu_grid.addWidget(field_block("Flash Attention", self.flash_attn, "Acelera contextos longos e reduz uso de VRAM."), 1, 0)
        gpu_grid.addWidget(field_block("Tipo do Cache KV", self.kv_cache, "Q8_0 reduz memória em contextos grandes com perda mínima."), 1, 1)
        gpu_grid.setColumnStretch(0, 1)
        gpu_grid.setColumnStretch(1, 1)
        gpu_box.addLayout(gpu_grid)
        self._sync_gpu_layers_state()
        parent_layout.addWidget(gpu_card)

        # Card 3: Context, Speed & Generation
        gen_card = container()
        gen_box = vertical(gen_card, (18, 16, 18, 16), 12)
        gen_box.addWidget(label("Contexto, velocidade e resposta", "sectionTitle"))
        gen_grid = QGridLayout()
        gen_grid.setHorizontalSpacing(16)
        gen_grid.setVerticalSpacing(12)

        self.controls["context"] = self._spin(0, 262144, self.repository.preference("context", 8192), " tokens", "Automático (do modelo)", step=1024)
        self.controls["response_tokens"] = self._spin(-1, 262144, self.repository.preference("response_tokens", -1), " tokens", "Usar seletor do chat", step=256)
        self.controls["batch"] = self._spin(0, 16384, self.repository.preference("batch", 512), " tokens", "Automático", step=128)
        self.controls["ubatch"] = self._spin(0, 8192, self.repository.preference("ubatch", 256), " tokens", "Automático", step=64)
        self.controls["threads"] = self._spin(0, 128, self.repository.preference("threads", default_cpu_threads()), " threads", "Automático")
        self.controls["threads_batch"] = self._spin(0, 128, self.repository.preference("threads_batch", default_batch_threads()), " threads", "Automático")

        temp_spin = QDoubleSpinBox()
        temp_spin.setRange(0.0, 2.0)
        temp_spin.setSingleStep(0.05)
        temp_spin.setDecimals(2)
        temp_spin.setValue(float(self.repository.preference("temperature", 0.6)))
        self.controls["temperature"] = temp_spin

        self.thinking_check = QCheckBox("Habilitar pensamento interno (thinking) do modelo")
        self.thinking_check.setChecked(bool(self.repository.preference("thinking", False)))

        gen_grid.addWidget(field_block("Janela de contexto", self.controls["context"], "8192+ recomendado para conversas longas e uso de ferramentas."), 0, 0)
        gen_grid.addWidget(field_block("Limite máximo da resposta", self.controls["response_tokens"], "-1 usa o seletor do chat (padrão Livre = sem corte); 0 = sem limite."), 0, 1)
        gen_grid.addWidget(field_block("Batch (processamento de prompt)", self.controls["batch"], "512 acelera a leitura do histórico e ferramentas."), 1, 0)
        gen_grid.addWidget(field_block("Microbatch", self.controls["ubatch"], "Valores menores reduzem o uso de memória; valores maiores podem aumentar o desempenho."), 1, 1)
        gen_grid.addWidget(field_block("Threads CPU (geração)", self.controls["threads"], "Recomendado: número de núcleos físicos (4 no i7-3770)."), 2, 0)
        gen_grid.addWidget(field_block("Threads CPU (prompt/batch)", self.controls["threads_batch"], "Pode usar todas as threads lógicas (8 no i7-3770)."), 2, 1)
        gen_grid.addWidget(field_block("Temperatura", temp_spin, "0.4–0.7 ideal para código e ferramentas precisas."), 3, 0)
        gen_grid.addWidget(field_block("Modo de raciocínio interno", self.thinking_check, "Desativado gera respostas diretas e mais rápidas."), 3, 1)
        gen_grid.setColumnStretch(0, 1)
        gen_grid.setColumnStretch(1, 1)
        gen_box.addLayout(gen_grid)
        parent_layout.addWidget(gen_card)

        # Card 4: Optional Limits (Disabled by default) + Live Runtime Status
        lim_card = container()
        lim_box = vertical(lim_card, (18, 16, 18, 16), 12)
        lim_box.addWidget(label("Limites opcionais (desativados por padrão)", "sectionTitle"))
        lim_box.addWidget(label("Mantenha em 0 (Sem limite) para uso livre total do hardware sem bloqueios do GameNext.", "silver", True))
        lim_grid = QGridLayout()
        lim_grid.setHorizontalSpacing(16)
        lim_grid.setVerticalSpacing(12)

        self.controls["vram"] = self._spin(0, 262144, self.repository.preference("vram", 0), " MiB", "Sem limite", step=512)
        self.controls["ram"] = self._spin(0, 524288, self.repository.preference("ram", 0), " MiB", "Sem limite", step=1024)

        lim_grid.addWidget(field_block("Alvo opcional de VRAM", self.controls["vram"], "0 = sem limite (usa toda a VRAM livre no modo automático)."), 0, 0)
        lim_grid.addWidget(field_block("Teto opcional de RAM privada", self.controls["ram"], "0 = sem limite no Windows Job Object."), 0, 1)
        lim_grid.setColumnStretch(0, 1)
        lim_grid.setColumnStretch(1, 1)
        lim_box.addLayout(lim_grid)

        self.applied = label("Em execução: nenhum modelo carregado no momento", "statusBadge", True)
        lim_box.addWidget(self.applied)
        if backend:
            backend.ready_changed.connect(
                lambda ready: self.applied.setText(
                    "Em execução: " + backend.gpu_summary if ready else "Em execução: nenhum modelo carregado no momento"
                )
            )
        parent_layout.addWidget(lim_card)

    def _build_data_tab(self, parent_layout, data_dir):
        card = container()
        box = vertical(card, (18, 16, 18, 16), 12)
        box.addWidget(label("Armazenamento e dados locais", "sectionTitle"))
        path = QLineEdit(str(data_dir))
        path.setReadOnly(True)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(path, 1)
        row.addWidget(button("Abrir pasta de dados", self._open_data_folder))
        box.addWidget(label("Pasta de histórico e logs", "fieldLabel"))
        box.addLayout(row)
        box.addWidget(label("Histórico salvo em SQLite local (WAL). Você pode exportar conversas em Markdown ou JSON pelo cabeçalho do chat.", "silver", True))
        box.addWidget(label("Sem telemetria. O servidor de inferência escuta exclusivamente em 127.0.0.1 com chave efêmera.", "muted", True))
        parent_layout.addWidget(card)

    def _open_data_folder(self):
        if os.name == "nt":
            os.startfile(str(self.data_dir), "open")

    @staticmethod
    def _spin(low: int, high: int, value: int, suffix: str = "", special: str = "", step: int = 1) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setSingleStep(step)
        if suffix:
            spin.setSuffix(suffix)
        if special:
            spin.setSpecialValueText(special)
        spin.setValue(int(value))
        return spin

    def _sync_gpu_layers_state(self):
        self.controls["gpu_layers"].setEnabled(self.gpu_mode.currentData() == "custom")

    def _update_hardware_banner(self, gpu_text: str):
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        cpu_threads = os.cpu_count() or 4
        self.hw_summary.setText(f"CPU: {cpu_threads} threads lógicas · RAM total: {ram_gb:.1f} GB · {gpu_text}")

    def apply_preset(self, preset: str):
        presets = {
            "recommended": {
                "gpu_mode": "auto", "gpu_layers": 99, "flash_attn": "auto", "kv_cache": "f16",
                "context": 8192, "response_tokens": -1, "batch": 512, "ubatch": 256,
                "threads": default_cpu_threads(), "threads_batch": default_batch_threads(),
                "temperature": 0.6, "thinking": False, "vram": 0, "ram": 0,
            },
            "max_gpu": {
                "gpu_mode": "gpu_all", "gpu_layers": 99, "flash_attn": "on", "kv_cache": "q8_0",
                "context": 8192, "response_tokens": -1, "batch": 512, "ubatch": 256,
                "threads": default_cpu_threads(), "threads_batch": default_batch_threads(),
                "temperature": 0.6, "thinking": False, "vram": 0, "ram": 0,
            },
            "hybrid_large": {
                "gpu_mode": "auto", "gpu_layers": 99, "flash_attn": "auto", "kv_cache": "q8_0",
                "context": 4096, "response_tokens": -1, "batch": 256, "ubatch": 128,
                "threads": default_cpu_threads(), "threads_batch": default_batch_threads(),
                "temperature": 0.6, "thinking": False, "vram": 0, "ram": 0,
            },
        }
        values = presets[preset]
        self.gpu_mode.setCurrentIndex(max(0, self.gpu_mode.findData(values["gpu_mode"])))
        self.flash_attn.setCurrentIndex(max(0, self.flash_attn.findData(values["flash_attn"])))
        self.kv_cache.setCurrentIndex(max(0, self.kv_cache.findData(values["kv_cache"])))
        self.thinking_check.setChecked(values["thinking"])
        for key in ("gpu_layers", "context", "response_tokens", "batch", "ubatch", "threads", "threads_batch", "vram", "ram", "temperature"):
            self.controls[key].setValue(values[key])
        self._sync_gpu_layers_state()
        self.save()
        self.notice.setText("Perfil aplicado e salvo. Descarregue e carregue o modelo se ele já estiver em execução.")

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Pasta de modelos")
        if path:
            self.folder.setText(path)

    def save(self):
        self.repository.set_preference("models_dir", self.folder.text())
        self.repository.set_preference("executable", self.model_panel.executable.text())
        self.repository.set_preference("gpu_mode", self.gpu_mode.currentData())
        self.repository.set_preference("flash_attn", self.flash_attn.currentData())
        self.repository.set_preference("kv_cache", self.kv_cache.currentData())
        self.repository.set_preference("thinking", self.thinking_check.isChecked())
        for key, control in self.controls.items():
            self.repository.set_preference(key, control.value())
        self.notice.setText("Preferências salvas. Recarregue o modelo para aplicar alterações no backend.")

    def performance_config(self):
        self.save()
        return {
            **{key: control.value() for key, control in self.controls.items()},
            "gpu_mode": self.gpu_mode.currentData(),
            "flash_attn": self.flash_attn.currentData(),
            "kv_cache": self.kv_cache.currentData(),
            "thinking": self.thinking_check.isChecked(),
            "device": "CPU" if self.gpu_mode.currentData() == "cpu" else "Vulkan",
        }

    def defaults(self):
        self.apply_preset("recommended")
        self.notice.setText("Padrões sem limitações restaurados e salvos.")
