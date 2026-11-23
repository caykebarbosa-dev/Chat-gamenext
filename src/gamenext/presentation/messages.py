"""Plain-text conversation rendering with collapsed code blocks, tools and token/cost metrics."""
import re
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QApplication, QHBoxLayout
from gamenext.domain.models import Message
from gamenext.presentation.components import label, button, vertical
from gamenext.presentation.containers import container


class MessageView(QWidget):
    def __init__(self, message: Message, repository=None, demo=False):
        super().__init__()
        self.message = message
        self.repository = repository
        self.layout_ = vertical(self, (0, 12, 0, 16), 9)
        user = message.role == "user"
        heading = QHBoxLayout()
        if user:
            heading.addStretch()
        if user:
            who = "Você"
        elif demo:
            who = "GameNext · demonstração"
        elif message.provider == "kilo":
            who = f"GameNext · Kilo · {message.model_name}" if message.model_name else "GameNext · Kilo Gateway"
        else:
            who = f"GameNext · local · {message.model_name}" if message.model_name else "GameNext · local"
        heading.addWidget(label(who, "muted"))
        if not user:
            heading.addStretch()
        self.layout_.addLayout(heading)
        self.tool_list = QWidget()
        self.tool_layout = vertical(self.tool_list, spacing=4)
        self.layout_.addWidget(self.tool_list)
        self.rendered_runs = 0
        self.body = label(message.content, wrap=True)
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setAlignment(Qt.AlignmentFlag.AlignRight if user else Qt.AlignmentFlag.AlignLeft)
        self.layout_.addWidget(self.body)
        for path in message.attachments:
            item = label("↳  " + Path(path).name, "silver")
            item.setToolTip(path)
            item.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.layout_.addWidget(item)
        self.status = label("", "muted")
        self.layout_.addWidget(self.status)
        if not user:
            self.metrics = container("messageMetrics")
            metrics_layout = QHBoxLayout(self.metrics)
            metrics_layout.setContentsMargins(12, 8, 12, 8)
            metrics_layout.setSpacing(16)
            self.sent_tokens = label("", "silver")
            self.received_tokens = label("", "silver")
            self.cost_label = label("", "silver")
            self.duration = label("", "silver")
            metrics_layout.addWidget(self.sent_tokens)
            metrics_layout.addWidget(self.received_tokens)
            metrics_layout.addWidget(self.cost_label)
            metrics_layout.addWidget(self.duration)
            metrics_layout.addStretch()
            self.metrics.setToolTip("Contagem de tokens e custo real informados pelo modelo/gateway.")
            self.layout_.addWidget(self.metrics)
        self.render_final()

    def update_text(self, text: str):
        self.body.setText(re.sub(r"\*\*(.+?)\*\*", r"\1", text))
        self.status.setText("Gerando resposta…")

    def render_final(self):
        for run in self.message.tool_runs[self.rendered_runs:]:
            details = label(run.get("summary", ""), "silver", True)
            details.setTextFormat(Qt.TextFormat.PlainText)
            details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            details.hide()
            title = button(("✓  " if run.get("ok") else "×  ") + run["tool"] + f" · {run.get('elapsed', 0):.1f} s", symbol="tasks")
            title.setCheckable(True)
            title.toggled.connect(details.setVisible)
            self.tool_layout.addWidget(title)
            self.tool_layout.addWidget(details)
        self.rendered_runs = len(self.message.tool_runs)
        if self.message.role == "assistant":
            self.sent_tokens.setText(f"Enviados  {self.message.prompt_tokens if self.message.prompt_tokens is not None else '—'} tokens")
            self.received_tokens.setText(f"Recebidos  {self.message.completion_tokens if self.message.completion_tokens is not None else '—'} tokens")
            if self.message.cost_brl is not None:
                if self.message.cost_brl == 0.0:
                    self.cost_label.setText("Grátis")
                elif self.message.cost_brl < 0.01:
                    self.cost_label.setText(f"R$ {self.message.cost_brl:.4f}".replace(".", ","))
                else:
                    self.cost_label.setText(f"R$ {self.message.cost_brl:.2f}".replace(".", ","))
                self.cost_label.show()
            else:
                self.cost_label.hide()
            elapsed = self.message.elapsed_seconds
            self.duration.setText(f"{elapsed:.1f} s" if elapsed is not None else "— s")
            self.metrics.setVisible(self.message.status != "processando")
        self.status.setText(self.message.status if self.message.status != "concluído" else "")
        parts = re.split(r"```([\w]*)\n(.*?)```", self.message.content, flags=re.S)
        if len(parts) < 3:
            self.body.setText(re.sub(r"\*\*(.+?)\*\*", r"\1", self.message.content))
            return
        self.body.setText(parts[0].strip())
        for index in range(1, len(parts), 3):
            language, code, tail = parts[index:index + 3]
            content = QWidget()
            code_layout = vertical(content)
            code_label = label(code.strip(), "silver", True)
            code_label.setTextFormat(Qt.TextFormat.PlainText)
            code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            code_layout.addWidget(code_label)
            code_layout.addWidget(button("Copiar código", lambda checked=False, c=code: QApplication.clipboard().setText(c.strip())))
            content.hide()
            key = "expanded:" + self.message.id + ":" + str(index)
            toggle = button(f"›  {language or 'Código'} · {len(code.splitlines())} linhas")
            toggle.setCheckable(True)
            def expand(checked, target=content, preference=key):
                target.setVisible(checked)
                if self.repository:
                    self.repository.set_preference(preference, checked)
            toggle.toggled.connect(expand)
            self.layout_.addWidget(toggle)
            self.layout_.addWidget(content)
            if self.repository:
                toggle.setChecked(self.repository.preference(key, False))
            if tail.strip():
                self.layout_.addWidget(label(tail.strip(), wrap=True))
        if self.message.role == "assistant":
            self.layout_.removeWidget(self.metrics)
            self.layout_.addWidget(self.metrics)
