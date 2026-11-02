from __future__ import annotations

from agentkit_core import TIERS, BuildContext, ModelRegistry, Provider, get_model
from agentkit_middleware import DecisionsClient, DecisionsSelector, SelectionMiddleware


def registry_tiers() -> tuple[str, ...]:
    return tuple(TIERS)


def decisions_middleware(
    ctx: BuildContext,
    registry: ModelRegistry,
    tier: str,
    system_prompt: str,
    *,
    with_models: bool,
    entry: str,
) -> SelectionMiddleware:
    """Decisions picks the visible tools and the model tier (tier -> model from the registry).

    `entry` is the registry entry name whose tiers the selector may switch between.
    """
    selector = DecisionsSelector(
        DecisionsClient(ctx.settings.require_key(Provider.OPENAI)),
        default_tier=tier,
        system_prompt=system_prompt,
    )
    models = (
        {t: get_model(registry.resolve(entry, t), ctx.settings) for t in registry_tiers()}
        if with_models
        else {}
    )
    return SelectionMiddleware(selector, models=models, default_tier=tier)
