"""Demonstration task state. No real tool progress is represented here."""
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget, QProgressBar, QHBoxLayout
from gamenext.domain.models import TaskPlan
from gamenext.presentation.components import label, button, vertical


class TaskPanel(QWidget):
    def __init__(self, repository):
        super().__init__()
        self.repository = repository
        self.plan = None
        self.setObjectName("tasks")
        self.setFixedWidth(270)
        layout = vertical(self, (20, 25, 20, 20), 16)
        layout.addWidget(label("Tarefas"))
        layout.addWidget(label("SIMULAÇÃO DA INTERFACE", "muted"))
        self.objective = label("Nenhuma tarefa iniciada", wrap=True)
        layout.addWidget(self.objective)
        self.count = label("", "silver")
        layout.addWidget(self.count)
        self.progress = QProgressBar()
        self.progress.setRange(0, 3)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.rows = [label("", "silver", True) for _ in range(3)]
        for row in self.rows:
            row.setMinimumHeight(42)
            layout.addWidget(row)
        row = QHBoxLayout()
        self.pause = button("Pausar", self.toggle)
        self.cancel = button("Cancelar", self.cancel_plan)
        row.addWidget(self.pause)
        row.addWidget(self.cancel)
        layout.addLayout(row)
        self.retry = button("Tentar novamente", self.restart)
        layout.addWidget(self.retry)
        layout.addStretch()
        layout.addWidget(label("Prévia de estados. Nenhuma ferramenta será executada.", "muted", True))
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.advance)
        self.refresh()

    def start(self, objective: str):
        self.plan = TaskPlan(objective)
        self.timer.start()
        self.refresh()

    def advance(self):
        if self.plan.completed < 3:
            self.plan.completed += 1
        if self.plan.completed == 3:
            self.plan.status = "concluída · simulação"
            self.timer.stop()
        self.refresh()

    def toggle(self):
        if self.timer.isActive():
            self.timer.stop()
            self.plan.status = "pausada"
        else:
            self.timer.start()
            self.plan.status = "simulação"
        self.refresh()

    def cancel_plan(self):
        self.timer.stop()
        if self.plan:
            self.plan.status = "cancelada"
        self.refresh()

    def restart(self):
        if self.plan:
            self.start(self.plan.objective)

    def refresh(self):
        p = self.plan
        self.pause.setEnabled(bool(p and p.completed < 3 and p.status != "cancelada"))
        self.cancel.setEnabled(bool(p and p.completed < 3 and p.status != "cancelada"))
        self.retry.setVisible(bool(p and (p.completed == 3 or p.status == "cancelada")))
        if not p:
            return
        self.objective.setText(p.objective[:160])
        self.count.setText(f"{p.completed} de 3 · {p.status}")
        self.progress.setValue(p.completed)
        for i, row in enumerate(self.rows):
            symbol = "✓" if i < p.completed else ("›" if i == p.completed else "·")
            row.setText(f"{symbol}  {p.steps[i]}")
        self.pause.setText("Pausar" if self.timer.isActive() else "Retomar")
        self.repository.set_preference("task_preview", {"objective": p.objective, "completed": p.completed, "status": p.status})

    def restore(self):
        saved = self.repository.preference("task_preview")
        if saved:
            self.plan = TaskPlan(saved["objective"], completed=saved["completed"], status=saved["status"])
            if self.plan.status == "simulação":
                self.plan.status = "pausada após reinício"
            self.refresh()
