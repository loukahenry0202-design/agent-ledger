from __future__ import annotations

from agent_ledger.guardrails.similarity import text_similarity


def compute_drift_score(objective: str, output: str) -> float:
    """
    Score de dérive naïf : 0 = aligné avec l'objectif, 1 = totalement hors-sujet.
    Basé sur 1 - similarité textuelle (sans API externe).
    """
    if not objective.strip():
        return 0.0
    if not output.strip():
        return 1.0
    similarity = text_similarity(objective, output)
    return max(0.0, min(1.0, 1.0 - similarity))
