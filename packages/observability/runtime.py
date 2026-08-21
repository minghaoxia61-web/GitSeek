from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock


def _percentile(values: deque[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 1)


@dataclass
class PathStats:
    requests: int = 0
    errors: int = 0
    total_duration_ms: float = 0.0
    recent_durations_ms: deque[float] = field(default_factory=lambda: deque(maxlen=1000))


@dataclass
class ExternalStats:
    calls: int = 0
    errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    total_duration_ms: float = 0.0


class RuntimeMetrics:
    def __init__(self) -> None:
        self.started_at = datetime.now(UTC)
        self._paths: dict[str, PathStats] = defaultdict(PathStats)
        self._external: dict[str, ExternalStats] = defaultdict(ExternalStats)
        self._lock = Lock()

    def record(self, path: str, status_code: int, duration_ms: float) -> None:
        with self._lock:
            stats = self._paths[path]
            stats.requests += 1
            stats.errors += int(status_code >= 500)
            stats.total_duration_ms += duration_ms
            stats.recent_durations_ms.append(duration_ms)

    def record_external(
        self,
        provider: str,
        *,
        duration_ms: float,
        error: bool,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        with self._lock:
            stats = self._external[provider]
            stats.calls += 1
            stats.errors += int(error)
            stats.input_tokens += max(0, input_tokens)
            stats.output_tokens += max(0, output_tokens)
            stats.estimated_cost_usd += max(0.0, estimated_cost_usd)
            stats.total_duration_ms += max(0.0, duration_ms)

    def snapshot(self) -> dict:
        with self._lock:
            paths = {
                path: {
                    "requests": stats.requests,
                    "errors": stats.errors,
                    "error_rate": round(stats.errors / stats.requests, 4),
                    "average_duration_ms": round(stats.total_duration_ms / stats.requests, 1),
                    "p50_duration_ms": _percentile(stats.recent_durations_ms, 0.50),
                    "p95_duration_ms": _percentile(stats.recent_durations_ms, 0.95),
                }
                for path, stats in sorted(self._paths.items())
                if stats.requests
            }
            external = {
                provider: {
                    "calls": stats.calls,
                    "errors": stats.errors,
                    "error_rate": round(stats.errors / stats.calls, 4),
                    "input_tokens": stats.input_tokens,
                    "output_tokens": stats.output_tokens,
                    "estimated_cost_usd": round(stats.estimated_cost_usd, 6),
                    "average_duration_ms": round(stats.total_duration_ms / stats.calls, 1),
                }
                for provider, stats in sorted(self._external.items())
                if stats.calls
            }
        return {
            "started_at": self.started_at,
            "uptime_seconds": max(0, int((datetime.now(UTC) - self.started_at).total_seconds())),
            "paths": paths,
            "external_services": external,
        }


runtime_metrics = RuntimeMetrics()
