"""Optional deepagents wiring with a restricted system prompt."""

from typing import Any

SUPERVISOR_INSTRUCTIONS = """
You orchestrate the focus-session workflow. You may read state, submit observations,
and send story text. You must not calculate or mutate stars, dungeon time, currency,
progress, or honor. Every entitlement change must use the rule service decision_id.
""".strip()


def build_supervisor(tools: list[Any], model: Any = None) -> Any:
    """Build a deepagents supervisor only when a model is configured."""
    from deepagents import create_deep_agent

    return create_deep_agent(model=model, tools=tools, system_prompt=SUPERVISOR_INSTRUCTIONS)
