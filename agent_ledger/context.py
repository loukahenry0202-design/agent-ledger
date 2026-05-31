from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar

_current_agent: ContextVar[str] = ContextVar("agent_ledger_agent", default="default")
_current_workflow: ContextVar[str | None] = ContextVar("agent_ledger_workflow", default=None)
_current_session_id: ContextVar[str] = ContextVar("agent_ledger_session", default="default")


def current_agent() -> str:
    return _current_agent.get()


def current_workflow() -> str | None:
    return _current_workflow.get()


def current_session_id() -> str:
    return _current_session_id.get()


@contextmanager
def agent_session(agent_id: str, workflow: str | None = None):
    """Contexte pour attribuer tous les appels enregistrés à un agent."""
    agent_token = _current_agent.set(agent_id)
    workflow_token = _current_workflow.set(workflow)
    session_token = _current_session_id.set(str(uuid.uuid4()))
    try:
        yield
    finally:
        _current_agent.reset(agent_token)
        _current_workflow.reset(workflow_token)
        _current_session_id.reset(session_token)
