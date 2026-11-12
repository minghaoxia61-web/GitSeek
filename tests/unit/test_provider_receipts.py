import asyncio
import json

import httpx
import pytest

from packages.agent_core.llm import AgentLLMError, ChatCompletionClient
from packages.embeddings.client import OpenAIEmbeddingClient
from packages.observability.calls import (
    ReceiptPersistenceError,
    UsageLedger,
    UsageUncertainError,
    token_count,
)


def response_payload(usage=True):
    payload = {
        "id": "response-1",
        "model": "actual-model",
        "choices": [{"message": {"content": "FINISH: done"}}],
    }
    if usage:
        payload["usage"] = {"prompt_tokens": 10, "completion_tokens": 5}
    return payload


@pytest.mark.parametrize("rates,expected", [((None, None), None), ((0, 0), 0), ((1, 2), 0.00002)])
def test_missing_prices_explicit_free_and_configured_estimate(rates, expected):
    events = []

    async def run():
        async def changed(event):
            events.append(event)

        ledger = UsageLedger(on_change=changed)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=response_payload()),
            )
        ) as http:
            provider = ledger.observe(
                ChatCompletionClient("private-key", model="requested", client=http),
                kind="chat",
                input_rate=rates[0],
                output_rate=rates[1],
            )
            await provider.complete([{"role": "user", "content": "hello"}])
        return ledger.snapshot()

    bill = asyncio.run(run())
    assert bill["estimated_cost_usd"] == expected
    assert bill["state"] == ("unknown" if expected is None else "known")
    assert [event["status"] for event in events] == ["started", "completed"]
    assert bill["calls"][0]["response_id"] == "response-1"
    assert bill["calls"][0]["provider_model"] == "actual-model"
    assert "private-key" not in json.dumps(bill)


def test_missing_usage_never_becomes_zero_and_prevents_followup_dispatch():
    attempts = []

    async def run():
        def handle(request):
            attempts.append(request)
            return httpx.Response(200, json=response_payload(usage=False))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            ledger = UsageLedger(token_budget=100)
            provider = ledger.observe(
                ChatCompletionClient("key", model="m", client=http),
                kind="chat",
                input_rate=0,
                output_rate=0,
            )
            result = await provider.complete([])
            assert result.input_tokens is None and result.output_tokens is None
            with pytest.raises(UsageUncertainError):
                await provider.complete([])
            return ledger.snapshot()

    bill = asyncio.run(run())
    assert len(attempts) == 1
    assert bill["estimated_cost_usd"] is None
    assert bill["unknown_usage_calls"] == 1


@pytest.mark.parametrize("mode", ["http", "network", "invalid_choices"])
def test_failed_provider_calls_preserve_observed_or_unknown_charges(mode):
    async def run():
        def handle(request):
            if mode == "network":
                raise httpx.ReadTimeout("timeout", request=request)
            if mode == "http":
                return httpx.Response(503, json={"error": "unavailable"})
            payload = response_payload()
            payload["choices"] = []
            return httpx.Response(200, json=payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            ledger = UsageLedger()
            provider = ledger.observe(
                ChatCompletionClient("key", model="m", client=http),
                kind="chat",
                input_rate=1,
                output_rate=2,
            )
            with pytest.raises(AgentLLMError):
                await provider.complete([])
            return ledger.snapshot()

    bill = asyncio.run(run())
    assert bill["calls"][0]["status"] == "failed"
    assert bill["calls"][0]["error_type"] == "AgentLLMError"
    assert bill["estimated_cost_usd"] == (0.00002 if mode == "invalid_choices" else None)


def test_enrichment_and_repair_share_budget_and_receipts():
    attempts = []

    async def run():
        def handle(request):
            attempts.append(request)
            return httpx.Response(200, json=response_payload())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            ledger = UsageLedger(token_budget=15)
            provider = ledger.observe(
                ChatCompletionClient("key", model="m", client=http),
                kind="chat",
                phase="issue_enrichment",
            )
            await provider.complete([])
            provider.phase = "repair"
            with pytest.raises(UsageUncertainError):
                await provider.complete([])
            return ledger.snapshot()

    bill = asyncio.run(run())
    assert len(attempts) == 1
    assert bill["chat_input_tokens"] == 10
    assert bill["calls"][0]["phase"] == "issue_enrichment"


@pytest.mark.parametrize("usage,expected", [(True, 0.000014), (False, None)])
def test_embedding_calls_are_included_and_missing_usage_is_unknown(usage, expected):
    async def run():
        payload = {"model": "embed-m", "data": [{"index": 0, "embedding": [1, 0]}]}
        if usage:
            payload["usage"] = {"total_tokens": 7}
        ledger = UsageLedger()
        client = OpenAIEmbeddingClient(
            "key",
            model="embed-m",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=payload),
            ),
        )
        provider = ledger.observe(client, kind="embedding", input_rate=2, output_rate=0)
        await provider.embed(["input"])
        await provider.aclose()
        return ledger.snapshot()

    bill = asyncio.run(run())
    assert bill["estimated_cost_usd"] == expected
    assert bill["calls"][0]["kind"] == "embedding"


def test_durable_checkpoint_failure_prevents_external_request():
    attempts = []

    async def run():
        async def checkpoint(event):
            raise OSError("storage unavailable")

        def handle(request):
            attempts.append(request)
            return httpx.Response(200, json=response_payload())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            ledger = UsageLedger(on_change=checkpoint)
            provider = ledger.observe(
                ChatCompletionClient("key", model="m", client=http), kind="chat"
            )
            with pytest.raises(OSError):
                await provider.complete([])
            with pytest.raises(ReceiptPersistenceError):
                await provider.complete([])
            assert ledger.snapshot()["persistence_failed"] is True

    asyncio.run(run())
    assert attempts == []


@pytest.mark.parametrize("value", [True, -1, "10", 2**53])
def test_invalid_usage_is_not_accepted_as_a_known_token_count(value):
    assert token_count(value) is None
