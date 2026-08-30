"""OpenAI-compatible chat client for the fixer agent loop.

Uses ``POST {base_url}/chat/completions`` rather than the ``/responses`` surface used by
:class:`packages.model_planning.OpenAIQueryPlanner`: coding models such as DeepSeek expose the
chat-completions API, and the fixer loop needs plain message round-trips instead of
schema-constrained JSON output.
"""

import json
from dataclasses import dataclass
from time import perf_counter
from types import TracebackType

import httpx

from packages.observability import runtime_metrics


class AgentLLMError(RuntimeError):
    pass


def _http_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return "provider returned a non-JSON error"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:240]
        if isinstance(error, str):
            return error[:240]
        if isinstance(payload.get("message"), str):
            return payload["message"][:240]
    return "provider did not include an error message"


@dataclass(frozen=True)
class ChatResult:
    content: str
    input_tokens: int
    output_tokens: int
    model: str


class ChatCompletionClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 180.0,
        client: httpx.AsyncClient | None = None,
        input_cost_per_million: float = 0.0,
        output_cost_per_million: float = 0.0,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout
        self._input_cost_per_million = max(0.0, input_cost_per_million)
        self._output_cost_per_million = max(0.0, output_cost_per_million)

    async def __aenter__(self) -> "ChatCompletionClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> ChatResult:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        request_started = perf_counter()
        request_failed = True
        input_tokens = 0
        output_tokens = 0
        try:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            response.raise_for_status()
            response_payload = response.json()
            usage = response_payload.get("usage", {})
            if isinstance(usage, dict):
                input_tokens = int(usage.get("prompt_tokens", 0) or 0)
                output_tokens = int(usage.get("completion_tokens", 0) or 0)
            choices = response_payload.get("choices")
            if not isinstance(choices, list) or not choices:
                raise AgentLLMError("model provider returned no choices")
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str) or not content.strip():
                raise AgentLLMError("model returned an empty message")
            request_failed = False
            return ChatResult(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=self.model,
            )
        except httpx.HTTPStatusError as exc:
            detail = _http_error_detail(exc.response)
            raise AgentLLMError(
                f"model provider returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise AgentLLMError(f"model provider network error: {type(exc).__name__}") from exc
        except (TypeError, KeyError, ValueError) as exc:
            raise AgentLLMError("model provider returned an unexpected payload") from exc
        finally:
            estimated_cost = (
                input_tokens * self._input_cost_per_million
                + output_tokens * self._output_cost_per_million
            ) / 1_000_000
            runtime_metrics.record_external(
                f"model:{self.model}",
                duration_ms=(perf_counter() - request_started) * 1000,
                error=request_failed,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimated_cost,
            )
            if owns_client:
                await client.aclose()
