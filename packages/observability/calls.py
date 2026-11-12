"""Per-run provider receipts. Unknown usage/prices never become a zero-cost estimate."""

import hashlib
import inspect
import json
import math
from datetime import UTC, datetime
from time import perf_counter


def content_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def token_count(value: object) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 2**53 - 1
        else None
    )


def estimated_cost(input_tokens, output_tokens, input_rate, output_rate) -> float | None:
    values = (input_rate, output_rate)
    if any(value is None or not math.isfinite(value) or value < 0 for value in values):
        return None
    if token_count(input_tokens) is None or token_count(output_tokens) is None:
        return None
    value = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
    return value if math.isfinite(value) else None


class UsageUncertainError(RuntimeError):
    pass


class ReceiptPersistenceError(OSError):
    pass


class UsageLedger:
    def __init__(self, *, on_change=None, token_budget: int | None = None):
        self.calls: list[dict] = []
        self.on_change = on_change
        self.token_budget = token_budget
        self.persistence_failed = False

    async def changed(self, call: dict) -> None:
        if self.on_change is not None:
            try:
                await self.on_change(dict(call))
            except Exception as exc:
                self.persistence_failed = True
                raise ReceiptPersistenceError("cannot persist provider receipt") from exc

    def snapshot(self) -> dict:
        costs = [call.get("estimated_cost_usd") for call in self.calls]
        complete = all(
            value is not None and call["status"] != "started"
            for value, call in zip(costs, self.calls, strict=True)
        )
        subtotal = sum(value for value in costs if value is not None)
        return {
            "version": "provider-billing-v1",
            "scope": "model_and_embeddings",
            "basis": "configured_rates_estimate",
            "is_invoice": False,
            "state": "known" if complete else "unknown",
            "estimated_cost_usd": subtotal if complete else None,
            "known_cost_subtotal_usd": subtotal,
            "call_count": len(self.calls),
            "unknown_cost_calls": sum(value is None for value in costs),
            "unknown_usage_calls": sum(not call.get("usage_known") for call in self.calls),
            "pending_calls": sum(call["status"] == "started" for call in self.calls),
            "persistence_failed": self.persistence_failed,
            "chat_input_tokens": sum(
                call.get("input_tokens") or 0 for call in self.calls if call["kind"] == "chat"
            ),
            "chat_output_tokens": sum(
                call.get("output_tokens") or 0 for call in self.calls if call["kind"] == "chat"
            ),
            "embedding_input_tokens": sum(
                call.get("input_tokens") or 0 for call in self.calls if call["kind"] == "embedding"
            ),
            "calls": [dict(call) for call in self.calls],
        }

    def observe(
        self, client, *, kind: str, input_rate=None, output_rate=None, phase: str = "repair"
    ):
        return ObservedProvider(client, self, kind, input_rate, output_rate, phase)


class ObservedProvider:
    def __init__(self, client, ledger, kind, input_rate, output_rate, phase):
        self.client = client
        self.ledger = ledger
        self.kind = kind
        self.input_rate = input_rate
        self.output_rate = output_rate
        self.phase = phase
        self.model = getattr(client, "model", "unreported")

    async def complete(self, messages, **kwargs):
        if self.ledger.persistence_failed:
            raise ReceiptPersistenceError("previous receipt write failed; no request dispatched")
        # A failed request with no usage cannot be followed by an implicit enrichment retry.
        chat = [call for call in self.ledger.calls if call["kind"] == "chat"]
        if any(not call.get("usage_known") for call in chat):
            raise UsageUncertainError(
                "previous model usage is unknown; no further request dispatched"
            )
        spent = sum(
            (call.get("input_tokens") or 0) + (call.get("output_tokens") or 0) for call in chat
        )
        if self.ledger.token_budget is not None and spent >= self.ledger.token_budget:
            raise UsageUncertainError("run token budget exhausted; no further request dispatched")
        return await self._call("complete", messages, kwargs)

    async def embed(self, inputs):
        if not inputs:
            return []
        if self.ledger.persistence_failed:
            raise ReceiptPersistenceError("previous receipt write failed; no request dispatched")
        return await self._call("embed", inputs, {})

    async def _call(self, method: str, payload, kwargs):
        if len(self.ledger.calls) >= 1000:
            raise UsageUncertainError("provider receipt limit reached")
        call = {
            "seq": len(self.ledger.calls) + 1,
            "kind": self.kind,
            "phase": self.phase,
            "model": self.model,
            "status": "started",
            "started_at": datetime.now(UTC).isoformat(),
            "request_sha256": content_sha256({"payload": payload, "parameters": kwargs}),
            "usage_known": False,
            "input_tokens": None,
            "output_tokens": None,
            "estimated_cost_usd": None,
            "input_rate_per_million": self.input_rate,
            "output_rate_per_million": self.output_rate,
        }
        self.ledger.calls.append(call)
        await self.ledger.changed(call)  # Durable start evidence before external dispatch.
        before = getattr(self.client, "last_receipt", None)
        started = perf_counter()
        try:
            result = await getattr(self.client, method)(payload, **kwargs)
            call["status"] = "completed"
            if method == "complete":
                call["input_tokens"] = token_count(result.input_tokens)
                call["output_tokens"] = token_count(result.output_tokens)
                call["response_sha256"] = hashlib.sha256(result.content.encode("utf-8")).hexdigest()
                call["response_preview"] = result.content[:4000]
                call["response_chars"] = len(result.content)
        except BaseException as exc:
            call["status"] = "failed"
            call["error_type"] = type(exc).__name__
            raise
        finally:
            receipt = getattr(self.client, "last_receipt", None)
            if receipt is not None and receipt is not before:
                for key in (
                    "input_tokens",
                    "output_tokens",
                    "response_id",
                    "provider_model",
                    "http_status",
                    "http_response_sha256",
                    "usage_known",
                ):
                    if key in receipt:
                        call[key] = receipt[key]
            call["usage_known"] = (
                token_count(call["input_tokens"]) is not None
                and token_count(call["output_tokens"]) is not None
            )
            call["estimated_cost_usd"] = estimated_cost(
                call["input_tokens"],
                call["output_tokens"],
                self.input_rate,
                self.output_rate,
            )
            call["duration_ms"] = int((perf_counter() - started) * 1000)
            call["completed_at"] = datetime.now(UTC).isoformat()
            await self.ledger.changed(call)
        return result

    async def aclose(self):
        close = getattr(self.client, "aclose", None)
        if close:
            result = close()
            if inspect.isawaitable(result):
                await result
