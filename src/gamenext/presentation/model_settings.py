"""Real GGUF catalog, runtime selection, device probing and unrestricted backend lifecycle."""
import re
from pathlib import Path
from PyQt6.QtCore import QProcess, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QLineEdit, QComboBox, QHBoxLayout, QFileDialog, QPlainTextEdit
from gamenext.infrastructure.catalog import CatalogScanner
from gamenext.presentation.components import label, button, vertical
from gamenext.presentation.containers import container, field_block


class ModelSettings(QWidget):
    catalog_changed = pyqtSignal(list)
    hardware_changed = pyqtSignal(str)

    def __init__(self, repository, backend, performance_config):
        super().__init__()
        self.repository, self.backend = repository, backend
        self.performance_config = performance_config
        self.scanner = None
        self.stopping = False
        self.catalog = []
        self.gpu_total = repository.preference("gpu_total", 8192)
        self.gpu_device = None
        self.gpu_name = ""

        outer = vertical(self, spacing=14)

        def section(title: str, subtitle: str = ""):
            card = container()
            content = vertical(card, (18, 16, 18, 16), 11)
            content.addWidget(label(title, "sectionTitle"))
            if subtitle:
                content.addWidget(label(subtitle, "silver", True))
            outer.addWidget(card)
            return content

        # Section 1: Model Library
        layout = section(
            "Biblioteca de modelos GGUF",
            "Escolha a pasta dos modelos locais e selecione o arquivo GGUF desejado.",
        )
        self.folder = QLineEdit(repository.preference("models_dir", str(Path(__file__).resolve().parents[3])))
        self.folder.setAccessibleName("Pasta dos modelos GGUF")
        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(button("Escolher pasta", self.choose_folder))
        folder_row.addWidget(button("Atualizar catálogo", self.scan))
        layout.addWidget(label("Pasta dos modelos", "fieldLabel"))
        layout.addLayout(folder_row)

        self.models = QComboBox()
        self.models.setAccessibleName("Modelo GGUF para carregar")
        self.models.currentIndexChanged.connect(self.select_model)
        layout.addWidget(field_block("Modelo selecionado", self.models))
        self.info = label("Procurando modelos…", "statusBadge", True)
        layout.addWidget(self.info)

        # Section 2: Runtime & GPU
        layout = section(
            "Runtime local e aceleração",
            "Motor nativo llama.cpp com suporte a GPU Vulkan (AMD/NVIDIA/Intel), modo híbrido GPU + RAM e CPU.",
        )
        default_exe = Path(__file__).resolve().parents[3] / "runtime/llama-vulkan/llama-server.exe"
        self.executable = QLineEdit(repository.preference("executable", str(default_exe)))
        self.executable.setAccessibleName("Caminho do llama-server.exe")
        exe_row = QHBoxLayout()
        exe_row.setSpacing(10)
        exe_row.addWidget(self.executable, 1)
        exe_row.addWidget(button("Escolher executável", self.choose_executable))
        exe_row.addWidget(button("Detectar GPU", self.probe))
        layout.addWidget(label("Executável llama-server.exe", "fieldLabel"))
        layout.addLayout(exe_row)
        self.hardware = label("GPU: verificando dispositivos Vulkan…", "statusBadge", True)
        layout.addWidget(self.hardware)

        # Section 3: Execution
        layout = section(
            "Execução do modelo",
            "Carregue qualquer GGUF válido sem travas artificiais de VRAM ou memória.",
        )
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.load_button = button("Carregar modelo", self.load)
        self.load_button.setObjectName("primaryControl")
        self.unload_button = button("Descarregar", self.unload)
        self.details_button = button("Detalhes do backend", self.toggle_details)
        actions.addWidget(self.load_button)
        actions.addWidget(self.unload_button)
        actions.addWidget(self.details_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.status = label("Nenhum modelo carregado", "statusBadge", True)
        layout.addWidget(self.status)
        self.resource_label = label("", "silver", True)
        layout.addWidget(self.resource_label)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(140)
        self.details.setMaximumHeight(220)
        self.details.hide()
        layout.addWidget(self.details)

        self.probe_process = QProcess(self)
        self.probe_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.probe_process.finished.connect(self.probe_finished)
        if backend:
            backend.state.connect(self.status.setText)
            backend.resources.connect(self.resource_label.setText)
            backend.ready_changed.connect(self.ready_changed)
            backend.failed.connect(lambda error: self.status.setText(error[:400]))
            self.scan()
            self.probe()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pasta dos modelos", self.folder.text())
        if folder:
            self.folder.setText(folder)
            self.scan()

    def choose_executable(self):
        path, _ = QFileDialog.getOpenFileName(self, "llama-server.exe", "", "Executável (*.exe)")
        if path:
            self.executable.setText(path)
            self.repository.set_preference("executable", path)
            self.probe()

    def scan(self):
        if self.scanner and self.scanner.isRunning():
            return
        self.repository.set_preference("models_dir", self.folder.text())
        self.info.setText("Lendo cabeçalhos GGUF…")
        self.scanner = CatalogScanner(self.folder.text(), self)
        self.scanner.found.connect(self.fill_catalog)
        self.scanner.failed.connect(self.info.setText)
        self.scanner.start()

    def fill_catalog(self, entries):
        if self.stopping:
            return
        self.catalog = [m for m in entries if not m.get("error")]
        saved = self.repository.preference("model_path", "")
        self.models.blockSignals(True)
        self.models.clear()
        for model in self.catalog:
            size_gb = model["bytes"] / 1073741824
            self.models.addItem(f"{model['name']}  ({size_gb:.2f} GB)", model["path"])
        if not self.catalog:
            self.info.setText(
                "Nenhum GGUF válido encontrado. Escolha outra pasta."
                + (" " + entries[0].get("error", "") if entries else "")
            )
        else:
            index = self.models.findData(saved)
            self.models.setCurrentIndex(max(0, index))
            self.select_model()
        self.models.blockSignals(False)
        self.catalog_changed.emit(self.catalog)

    def select_model(self):
        index = self.models.currentIndex()
        if 0 <= index < len(self.catalog):
            entry = self.catalog[index]
            self.repository.set_preference("model_path", entry["path"])
            meta = entry.get("metadata", {})
            arch = meta.get("general.architecture", "desconhecida")
            size_gb = entry["bytes"] / 1073741824
            size_mib = entry["bytes"] / 1048576
            blocks = next((v for k, v in meta.items() if k.endswith(".block_count")), None)
            ctx_max = next((v for k, v in meta.items() if k.endswith(".context_length")), None)
            parts = [f"{size_gb:.2f} GB", f"arquitetura {arch}"]
            if blocks:
                parts.append(f"{blocks} camadas")
            if ctx_max:
                parts.append(f"contexto nativo até {ctx_max:,}".replace(",", "."))
            if self.gpu_total and size_mib < self.gpu_total * 0.78:
                parts.append("cabe 100% na GPU")
            elif self.gpu_total:
                parts.append("rodará em modo híbrido GPU + RAM")
            self.info.setText(" · ".join(parts))

    def probe(self):
        path = Path(self.executable.text())
        if not path.is_file():
            self.hardware.setText("Runtime não encontrado. Escolha llama-server.exe.")
            return
        if self.probe_process.state() != QProcess.ProcessState.NotRunning:
            return
        self.gpu_device = None
        self.gpu_name = ""
        self.probe_process.setWorkingDirectory(str(path.parent))
        self.probe_process.start(str(path), ["--list-devices"])

    def probe_finished(self):
        if self.stopping:
            return
        text = bytes(self.probe_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        match = re.search(r"\b((?:Vulkan|CUDA|ROCm|SYCL)\d+):\s*([^\r\n(]+?)\s*\((\d+)\s*MiB(?:,\s*(\d+)\s*MiB free)?", text, re.I)
        if match:
            self.gpu_device = match[1]
            self.gpu_name = match[2].strip()
            self.gpu_total = int(match[3])
            free_info = f", {match[4]} MiB livres" if match[4] else ""
            summary = f"{self.gpu_device}: {self.gpu_name} ({self.gpu_total} MiB VRAM{free_info})"
            self.hardware.setText(summary)
            self.repository.set_preference("gpu_total", self.gpu_total)
            self.hardware_changed.emit(summary)
            self.select_model()
        else:
            summary = "Nenhuma GPU Vulkan detectada — execução em CPU disponível normalmente."
            self.hardware.setText(summary)
            self.hardware_changed.emit(summary)

    def load(self, checked=False):
        if not self.backend:
            return False
        model = self.models.currentData()
        if not model:
            self.status.setText("Escolha um modelo GGUF válido")
            return False
        config = self.performance_config()
        config.update(
            executable=self.executable.text(),
            model=model,
            gpu_device=self.gpu_device or "",
            gpu_total=self.gpu_total,
        )
        self.repository.set_preference("executable", self.executable.text())
        try:
            self.backend.load(config)
            self.load_button.setEnabled(False)
            return True
        except (ValueError, OSError) as error:
            self.status.setText(str(error))
            return False

    def unload(self):
        if self.backend:
            self.backend.unload()
            self.status.setText("Modelo descarregado · recursos liberados")

    def ready_changed(self, ready):
        running = self.backend.process.state() != QProcess.ProcessState.NotRunning
        self.load_button.setEnabled(not running)
        if not ready:
            QTimer.singleShot(
                250,
                lambda: self.load_button.setEnabled(self.backend.process.state() == QProcess.ProcessState.NotRunning),
            )

    def toggle_details(self):
        if self.backend:
            self.details.setPlainText(self.backend.logs)
        visible = not self.details.isVisible()
        self.details.setVisible(visible)
        self.details_button.setText("Ocultar detalhes" if visible else "Detalhes do backend")

    def shutdown(self):
        self.stopping = True
        if self.scanner and self.scanner.isRunning():
            self.scanner.requestInterruption()
            self.scanner.wait(3000)
        if self.probe_process.state() != QProcess.ProcessState.NotRunning:
            self.probe_process.kill()
            self.probe_process.waitForFinished(1000)
