"""Wrapper optionnel autour du client OpenAI (pip install openai)."""

from __future__ import annotations

from typing import Any

from agent_ledger.context import current_agent, current_workflow
from agent_ledger.ledger import Ledger


class TrackedOpenAI:
    """Proxy minimal : enregistre chaque chat.completions.create."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.chat = _ChatProxy(client.chat)


class _ChatProxy:
    def __init__(self, chat: Any) -> None:
        self.completions = _CompletionsProxy(chat.completions)


class _CompletionsProxy:
    def __init__(self, completions: Any) -> None:
        self._completions = completions

    def create(self, *args: Any, **kwargs: Any) -> Any:
        response = self._completions.create(*args, **kwargs)
        model = kwargs.get("model") or getattr(response, "model", "unknown")
        usage = getattr(response, "usage", None)
        if usage:
            Ledger.get().record(
                model=str(model),
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                agent_id=current_agent(),
                workflow=current_workflow(),
                metadata={"provider": "openai"},
            )
        return response
