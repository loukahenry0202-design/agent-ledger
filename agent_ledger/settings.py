"""Chargement centralisé de la configuration via variables d'environnement."""

from __future__ import annotations

import os
from pathlib import Path


def load_env() -> None:
    """Charge `.env` si python-dotenv est disponible."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def resolve_database_path(default: str | Path | None = None) -> Path:
    """Résout le chemin SQLite depuis DATABASE_URL ou AGENT_LEDGER_DB."""
    load_env()
    default_path = Path(default or Path.home() / ".agent_ledger" / "ledger.db")

    raw = os.environ.get("DATABASE_URL") or os.environ.get("AGENT_LEDGER_DB")
    if not raw:
        return default_path

    if raw.startswith("sqlite:///"):
        return Path(raw.removeprefix("sqlite:///"))
    return Path(raw)
