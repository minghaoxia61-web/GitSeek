import inspect
from collections import defaultdict
from dataclasses import dataclass
from functools import wraps
from typing import Any, Literal

from packages.github_client import GitHubAPIError, GitHubRateLimitError

FaultKind = Literal["timeout", "rate_limit", "api_error"]


@dataclass(frozen=True)
class FaultRule:
    method: str
    kind: FaultKind
    fail_on_calls: tuple[int, ...] = (1,)
    reset_at: int | None = None

    def __post_init__(self) -> None:
        if not self.method:
            raise ValueError("fault rule method cannot be empty")
        if not self.fail_on_calls or any(call < 1 for call in self.fail_on_calls):
            raise ValueError("fault rule call numbers must be positive")


class FaultInjectingClient:
    """Deterministic proxy for exercising external-service degradation paths."""

    def __init__(self, delegate: Any, *rules: FaultRule) -> None:
        self._delegate = delegate
        self._rules = {rule.method: rule for rule in rules}
        if len(self._rules) != len(rules):
            raise ValueError("only one fault rule is allowed per method")
        self._calls: defaultdict[str, int] = defaultdict(int)

    def call_count(self, method: str) -> int:
        return self._calls[method]

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._delegate, name)
        if not callable(attribute):
            return attribute
        rule = self._rules.get(name)
        if rule is None:
            return attribute

        @wraps(attribute)
        async def injected(*args: Any, **kwargs: Any) -> Any:
            self._calls[name] += 1
            if self._calls[name] in rule.fail_on_calls:
                if rule.kind == "rate_limit":
                    raise GitHubRateLimitError(
                        "injected GitHub rate limit",
                        reset_at=rule.reset_at,
                    )
                if rule.kind == "timeout":
                    raise GitHubAPIError("injected GitHub timeout")
                raise GitHubAPIError("injected GitHub API failure")
            result = attribute(*args, **kwargs)
            return await result if inspect.isawaitable(result) else result

        return injected
