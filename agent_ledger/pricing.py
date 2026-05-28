"""Tarifs par million de tokens (USD) — mis à jour manuellement ou via config."""

from __future__ import annotations

# input $/1M tokens, output $/1M tokens
DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "unknown": (1.00, 3.00),
}


def normalize_model(model: str) -> str:
    base = model.split("/")[-1].lower()
    for key in DEFAULT_PRICING:
        if key != "unknown" and key in base:
            return key
    return base if base in DEFAULT_PRICING else "unknown"


def compute_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    pricing: dict[str, tuple[float, float]] | None = None,
) -> float:
    table = pricing or DEFAULT_PRICING
    key = normalize_model(model)
    in_rate, out_rate = table.get(key, table["unknown"])
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
