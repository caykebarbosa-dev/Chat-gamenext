"""UI-independent conversation and task data contracts."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from uuid import uuid4


def new_id() -> str:
    return str(uuid4())


@dataclass
class Message:
    role: str
    content: str
    attachments: list[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    status: str = "concluído"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    elapsed_seconds: float | None = None
    tool_runs: list[dict] = field(default_factory=list)
    provider: str = "local"
    model_name: str | None = None
    cost_usd: float | None = None
    cost_brl: float | None = None

    def serialize(self) -> dict:
        return asdict(self)


@dataclass
class TaskPlan:
    objective: str
    steps: list[str] = field(default_factory=lambda: [
        "Organizar o objetivo", "Preparar o plano", "Apresentar a prévia"
    ])
    completed: int = 0
    status: str = "simulação"
