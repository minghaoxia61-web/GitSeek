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


@dataclass(frozen=True)
class SearchEvent:
    recorded_at: datetime
    cache_hit: bool
    github_attempted: bool
    github_degraded: bool
    total_duration_ms: float
    channel_latency_ms: dict[str, float]


class RuntimeMetrics:
    def __init__(self) -> None:
        self.started_at = datetime.now(UTC)
        self._paths: dict[str, PathStats] = defaultdict(PathStats)
        self._external: dict[str, ExternalStats] = defaultdict(ExternalStats)
        self._search_events: deque[SearchEvent] = deque(maxlen=1000)
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

    def record_search(
        self,
        *,
        cache_hit: bool,
        github_attempted: bool,
        github_degraded: bool,
        total_duration_ms: float,
        channel_latency_ms: dict[str, float] | None = None,
        recorded_at: datetime | None = None,
    ) -> None:
        with self._lock:
            self._search_events.append(
                SearchEvent(
                    recorded_at=recorded_at or datetime.now(UTC),
                    cache_hit=cache_hit,
                    github_attempted=github_attempted,
                    github_degraded=github_degraded,
                    total_duration_ms=max(0.0, total_duration_ms),
                    channel_latency_ms={
                        key: max(0.0, value) for key, value in (channel_latency_ms or {}).items()
                    },
                )
            )

    @staticmethod
    def _search_snapshot(events: list[SearchEvent]) -> dict:
        if not events:
            return {
                "searches": 0,
                "cache_hits": 0,
                "cache_hit_rate": 0.0,
                "github_attempted_searches": 0,
                "github_degraded_searches": 0,
                "github_degradation_rate": 0.0,
                "average_duration_ms": 0.0,
                "p50_duration_ms": 0.0,
                "p95_duration_ms": 0.0,
                "channels": {},
                "trend": [],
            }
        durations = deque((event.total_duration_ms for event in events), maxlen=1000)
        attempted = [event for event in events if event.github_attempted]
        channel_values: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=1000))
        for event in events:
            for channel, duration in event.channel_latency_ms.items():
                channel_values[channel].append(duration)
        channels = {
            channel: {
                "calls": len(values),
                "average_duration_ms": round(sum(values) / len(values), 1),
                "p50_duration_ms": _percentile(values, 0.50),
                "p95_duration_ms": _percentile(values, 0.95),
            }
            for channel, values in sorted(channel_values.items())
        }
        buckets: dict[str, list[SearchEvent]] = defaultdict(list)
        for event in events:
            minute = event.recorded_at.astimezone(UTC).replace(second=0, microsecond=0)
            buckets[minute.isoformat()].append(event)
        trend = []
        for minute, bucket in sorted(buckets.items())[-60:]:
            bucket_attempted = [event for event in bucket if event.github_attempted]
            bucket_durations = deque(
                (event.total_duration_ms for event in bucket), maxlen=len(bucket)
            )
            trend.append(
                {
                    "minute": minute,
                    "searches": len(bucket),
                    "cache_hit_rate": round(
                        sum(event.cache_hit for event in bucket) / len(bucket), 4
                    ),
                    "github_degradation_rate": round(
                        sum(event.github_degraded for event in bucket_attempted)
                        / len(bucket_attempted),
                        4,
                    )
                    if bucket_attempted
                    else 0.0,
                    "p95_duration_ms": _percentile(bucket_durations, 0.95),
                }
            )
        return {
            "searches": len(events),
            "cache_hits": sum(event.cache_hit for event in events),
            "cache_hit_rate": round(sum(event.cache_hit for event in events) / len(events), 4),
            "github_attempted_searches": len(attempted),
            "github_degraded_searches": sum(event.github_degraded for event in attempted),
            "github_degradation_rate": round(
                sum(event.github_degraded for event in attempted) / len(attempted), 4
            )
            if attempted
            else 0.0,
            "average_duration_ms": round(sum(durations) / len(durations), 1),
            "p50_duration_ms": _percentile(durations, 0.50),
            "p95_duration_ms": _percentile(durations, 0.95),
            "channels": channels,
            "trend": trend,
        }

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
            search = self._search_snapshot(list(self._search_events))
        return {
            "started_at": self.started_at,
            "uptime_seconds": max(0, int((datetime.now(UTC) - self.started_at).total_seconds())),
            "paths": paths,
            "external_services": external,
            "search": search,
        }


runtime_metrics = RuntimeMetrics()
