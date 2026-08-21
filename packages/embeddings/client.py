from time import perf_counter
from types import TracebackType

import httpx
from pydantic import BaseModel, Field, SecretStr

from packages.observability import runtime_metrics


class EmbeddingAPIError(RuntimeError):
    pass


class EmbeddingItem(BaseModel):
    index: int
    embedding: list[float] = Field(min_length=1)


class EmbeddingResponse(BaseModel):
    data: list[EmbeddingItem]
    model: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class OpenAIEmbeddingClient:
    def __init__(
        self,
        api_key: SecretStr | str,
        *,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
        cost_per_million: float = 0.0,
    ) -> None:
        token = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._cost_per_million = max(0.0, cost_per_million)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> "OpenAIEmbeddingClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed(self, inputs: list[str]) -> list[list[float]]:
        if not inputs:
            return []
        request_started = perf_counter()
        input_tokens = 0
        try:
            response = await self._client.post(
                "/embeddings",
                json={"model": self.model, "input": inputs, "encoding_format": "float"},
            )
            response.raise_for_status()
            payload = EmbeddingResponse.model_validate(response.json())
            input_tokens = int(
                payload.usage.get("prompt_tokens", payload.usage.get("total_tokens", 0))
            )
        except (httpx.HTTPError, ValueError) as error:
            runtime_metrics.record_external(
                f"embedding:{self.model}",
                duration_ms=(perf_counter() - request_started) * 1000,
                error=True,
            )
            raise EmbeddingAPIError("embedding provider request failed") from error
        ordered = sorted(payload.data, key=lambda item: item.index)
        if len(ordered) != len(inputs):
            runtime_metrics.record_external(
                f"embedding:{self.model}",
                duration_ms=(perf_counter() - request_started) * 1000,
                error=True,
                input_tokens=input_tokens,
            )
            raise EmbeddingAPIError("embedding provider returned an incomplete batch")
        dimensions = len(ordered[0].embedding)
        if any(len(item.embedding) != dimensions for item in ordered):
            runtime_metrics.record_external(
                f"embedding:{self.model}",
                duration_ms=(perf_counter() - request_started) * 1000,
                error=True,
                input_tokens=input_tokens,
            )
            raise EmbeddingAPIError("embedding provider returned inconsistent dimensions")
        runtime_metrics.record_external(
            f"embedding:{self.model}",
            duration_ms=(perf_counter() - request_started) * 1000,
            error=False,
            input_tokens=input_tokens,
            estimated_cost_usd=input_tokens * self._cost_per_million / 1_000_000,
        )
        return [item.embedding for item in ordered]
