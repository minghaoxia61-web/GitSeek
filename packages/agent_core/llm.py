"""OpenAI-compatible chat client for the fixer agent loop.

Uses ``POST {base_url}/chat/completions`` rather than the ``/responses`` surface used by
:class:`packages.model_planning.OpenAIQueryPlanner`: coding models such as DeepSeek expose the
chat-completions API, and the fixer loop needs plain message round-trips instead of
schema-constrained JSON output.
"""

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter
from types import TracebackType

import httpx

from packages.observability import runtime_metrics
from packages.observability.calls import estimated_cost, token_count


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
    input_tokens: int | None
    output_tokens: int | None
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
        input_cost_per_million: float | None = None,
        output_cost_per_million: float | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout
        self._input_cost_per_million = input_cost_per_million
        self._output_cost_per_million = output_cost_per_million
        self.last_receipt = None

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
        input_tokens = None
        output_tokens = None
        self.last_receipt = {}
        try:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            self.last_receipt["http_status"] = response.status_code
            self.last_receipt["http_response_sha256"] = hashlib.sha256(response.content).hexdigest()
            response.raise_for_status()
            response_payload = response.json()
            if not isinstance(response_payload, dict):
                raise AgentLLMError("model provider returned a non-object payload")
            usage = response_payload.get("usage", {})
            if isinstance(usage, dict):
                input_tokens = token_count(usage.get("prompt_tokens"))
                output_tokens = token_count(usage.get("completion_tokens"))
            self.last_receipt["response_id"] = response_payload.get("id")
            self.last_receipt["provider_model"] = response_payload.get("model")
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
            detail = _http_error_detail(exc.response).replace(self._api_key, "[redacted]")
            raise AgentLLMError(
                f"model provider returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise AgentLLMError(f"model provider network error: {type(exc).__name__}") from exc
        except (TypeError, KeyError, ValueError) as exc:
            raise AgentLLMError("model provider returned an unexpected payload") from exc
        finally:
            cost = estimated_cost(
                input_tokens,
                output_tokens,
                self._input_cost_per_million,
                self._output_cost_per_million,
            )
            self.last_receipt.update(
                {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "usage_known": input_tokens is not None and output_tokens is not None,
                }
            )
            runtime_metrics.record_external(
                f"model:{self.model}",
                duration_ms=(perf_counter() - request_started) * 1000,
                error=request_failed,
                input_tokens=input_tokens or 0,
                output_tokens=output_tokens or 0,
                estimated_cost_usd=cost,
            )
            if owns_client:
                await client.aclose()
