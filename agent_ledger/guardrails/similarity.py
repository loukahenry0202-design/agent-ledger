from __future__ import annotations

import re
from math import sqrt


def tokenize(text: str) -> set[str]:
    """Tokenisation simple sans dépendance externe."""
    return set(re.findall(r"[a-zA-Z0-9àâäéèêëïîôùûüç]+", text.lower()))


def jaccard_similarity(a: str, b: str) -> float:
    """Similarité de Jaccard entre deux textes (0 = différent, 1 = identique)."""
    if not a.strip() or not b.strip():
        return 0.0
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def cosine_similarity_tokens(a: str, b: str) -> float:
    """Similarité cosinus naïve sur bags-of-words."""
    if not a.strip() or not b.strip():
        return 0.0
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    vocab = ta | tb
    va = [1 if t in ta else 0 for t in vocab]
    vb = [1 if t in tb else 0 for t in vocab]
    dot = sum(x * y for x, y in zip(va, vb))
    na = sqrt(sum(x * x for x in va))
    nb = sqrt(sum(y * y for y in vb))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def text_similarity(a: str, b: str) -> float:
    """Score combiné Jaccard + cosinus."""
    j = jaccard_similarity(a, b)
    c = cosine_similarity_tokens(a, b)
    return (j + c) / 2
