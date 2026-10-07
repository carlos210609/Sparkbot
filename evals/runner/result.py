from dataclasses import dataclass, field
from typing import Any

@dataclass
class EvaluationResult:
    scenario_id: str
    passed: bool
    steps: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    verified: bool = False
    hallucinated_result: bool = False
    recovered: bool = False
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()
