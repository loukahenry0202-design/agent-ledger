from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from agent_ledger.context import agent_session
from agent_ledger.ledger import Ledger

F = TypeVar("F", bound=Callable[..., Any])


def track_agent(agent_id: str, workflow: str | None = None) -> Callable[[F], F]:
    """Décorateur : attribue le coût de la fonction à un agent."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with agent_session(agent_id, workflow=workflow):
                return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def track_llm_call(
    model: str,
    *,
    agent_id: str | None = None,
    workflow: str | None = None,
) -> Callable[[F], F]:
    """Enregistre automatiquement si la fonction retourne un dict usage OpenAI-like."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            usage = _extract_usage(result)
            if usage:
                Ledger.get().record(
                    model=model,
                    input_tokens=usage[0],
                    output_tokens=usage[1],
                    agent_id=agent_id,
                    workflow=workflow,
                )
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def _extract_usage(result: Any) -> tuple[int, int] | None:
    if hasattr(result, "usage") and result.usage:
        u = result.usage
        return (
            getattr(u, "prompt_tokens", 0) or getattr(u, "input_tokens", 0),
            getattr(u, "completion_tokens", 0) or getattr(u, "output_tokens", 0),
        )
    if isinstance(result, dict) and "usage" in result:
        u = result["usage"]
        return (
            u.get("prompt_tokens", u.get("input_tokens", 0)),
            u.get("completion_tokens", u.get("output_tokens", 0)),
        )
    return None
