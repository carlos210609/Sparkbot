from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class Scenario:
    id: str
    category: str
    prompt: str
    expected: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    difficulty: str = "medium"
    max_steps: int = 20

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("scenario id cannot be empty")
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")
