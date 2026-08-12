from types import TracebackType

import httpx
from pydantic import BaseModel, Field, SecretStr


class EmbeddingAPIError(RuntimeError):
    pass


class EmbeddingItem(BaseModel):
    index: int
    embedding: list[float] = Field(min_length=1)


class EmbeddingResponse(BaseModel):
    data: list[EmbeddingItem]
    model: str | None = None


class OpenAIEmbeddingClient:
    def __init__(
        self,
        api_key: SecretStr | str,
        *,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        token = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
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
        try:
            response = await self._client.post(
                "/embeddings",
                json={"model": self.model, "input": inputs, "encoding_format": "float"},
            )
            response.raise_for_status()
            payload = EmbeddingResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise EmbeddingAPIError("embedding provider request failed") from error
        ordered = sorted(payload.data, key=lambda item: item.index)
        if len(ordered) != len(inputs):
            raise EmbeddingAPIError("embedding provider returned an incomplete batch")
        dimensions = len(ordered[0].embedding)
        if any(len(item.embedding) != dimensions for item in ordered):
            raise EmbeddingAPIError("embedding provider returned inconsistent dimensions")
        return [item.embedding for item in ordered]
