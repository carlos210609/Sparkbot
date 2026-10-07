from collections.abc import Iterable
from dataclasses import dataclass
from .result import EvaluationResult

@dataclass(frozen=True)
class BenchmarkMetrics:
    completion_correctness: float
    undetected_error_rate: float
    execution_hallucination_rate: float
    failure_recovery_rate: float
    average_steps: float
    average_cost: float
    average_latency_ms: float

    def to_dict(self) -> dict[str, float]:
        return self.__dict__.copy()

def calculate_metrics(results: Iterable[EvaluationResult]) -> BenchmarkMetrics:
    rows=list(results)
    if not rows:
        return BenchmarkMetrics(0,0,0,0,0,0,0)
    n=len(rows)
    return BenchmarkMetrics(sum(r.passed for r in rows)/n,sum((not r.passed and r.verified) for r in rows)/n,sum(r.hallucinated_result for r in rows)/n,sum(r.recovered for r in rows)/n,sum(r.steps for r in rows)/n,sum(r.cost for r in rows)/n,sum(r.latency_ms for r in rows)/n)
