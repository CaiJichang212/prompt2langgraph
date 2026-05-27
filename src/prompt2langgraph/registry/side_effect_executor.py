"""Side effect handler with approval interrupt support."""

from __future__ import annotations

from typing import Any

from prompt2langgraph.diagnostics.codes import E_SIDE_008
from prompt2langgraph.ir.models import SecurityPolicy
from prompt2langgraph.registry.executors import ExecutorError

# Internal signal keys — never written to workflow state.
# The compiler wrapper strips these keys before passing inputs to the actual executor.
_SIDE_EFFECT_APPROVED_KEY = "__pt2lg_side_effect_approved__"
_SIDE_EFFECT_REJECTED_KEY = "__pt2lg_side_effect_rejected__"


def side_effect_handler(
    inputs: dict[str, Any],
    params: dict[str, Any],
    *,
    security: SecurityPolicy | None = None,
    allow_side_effects: bool = False,
    node_id: str,
    executor_ref: str,
) -> dict[str, Any]:
    """Handle side effect node with approval interrupt.

    Returns:
        dict with one of:
        - ``{__pt2lg_side_effect_approved__: True, "inputs": inputs, "params": params}``
          when approval is granted or allow_side_effects=True;
        - ``{__pt2lg_side_effect_rejected__: True, "reason": str}``
          when the approver rejects;
        - raises ``ExecutorError(E_SIDE_008)`` as a defensive fallback.

    The ``__pt2lg_side_effect_approved__`` and ``__pt2lg_side_effect_rejected__``
    keys are internal signals consumed by the compiler wrapper; they are never
    written to workflow state.
    """
    security = security or SecurityPolicy()

    # Case 1: allow_side_effects=True bypasses approval
    if allow_side_effects:
        return {_SIDE_EFFECT_APPROVED_KEY: True, "inputs": inputs, "params": params}

    # Case 2 & 3: requires_approval or idempotency_key triggers interrupt
    # (P1: idempotency_key still uses approval path; P2 adds dedup)
    if security.requires_approval or security.idempotency_key:
        from langgraph.types import interrupt

        decision = interrupt(
            {
                "kind": "side_effect_approval",
                "node_id": node_id,
                "executor_ref": executor_ref,
                "action": params.get("action", "side_effect"),
                "inputs": inputs,
                "params": params,
                "idempotency_key": security.idempotency_key,
            }
        )
        approved, reason = _parse_decision(decision)
        if approved:
            return {_SIDE_EFFECT_APPROVED_KEY: True, "inputs": inputs, "params": params}
        return {_SIDE_EFFECT_REJECTED_KEY: True, "reason": reason}

    # Case 4: no approval and not allowed - raise defensive error
    raise ExecutorError(
        E_SIDE_008,
        f"side_effect node '{node_id}' requires approval or idempotency key",
        node_id=node_id,
        executor_ref=executor_ref,
    )


def _parse_decision(decision: Any) -> tuple[bool, str]:
    """Parse the resume payload into (approved, reason) tuple.

    Returns (True, "") on approval, (False, reason) on rejection.
    """
    if isinstance(decision, dict):
        if decision.get("decision") == "approved":
            return True, ""
        reason = decision.get("reason", "rejected by approver")
        if decision.get("decision") != "rejected":
            reason = f"unrecognized decision format: {decision}"
        return False, reason
    if decision == "approved":
        return True, ""
    if decision == "rejected":
        return False, "rejected by approver"
    return False, f"unrecognized decision: {decision!r}"
