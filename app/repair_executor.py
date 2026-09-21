"""
Repair executor.

Takes a FailureSignature, looks up candidate actions from the RepairLibrary,
applies them in order, and records success/failure.

The executor does not implement the actions themselves. It calls a
registered handler for each action type. This keeps the executor testable
and the actions pluggable.

Supported action types (handlers injected at construction):
- retry_with_backoff
- switch_harness
- inject_context
- rerun_with_verifier
- escalate
"""

import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.failure_classifier import FailureSignature
from app.repair_library import RepairAction, RepairLibrary
from app.schema import TraceEvent, EventType


@dataclass
class RepairOutcome:
    attempted: bool
    action_id: Optional[str]
    succeeded: bool
    events: list[TraceEvent] = field(default_factory=list)
    detail: str = ""


class RepairExecutor:
    """
    Executes repairs for a failure signature.

    Handlers are injected as a dict {action_type: callable}.
    Each callable receives (action: RepairAction, context: dict)
    and returns (succeeded: bool, detail: str).
    """

    def __init__(
        self,
        library: RepairLibrary,
        handlers: dict[str, Callable],
    ):
        self.library = library
        self.handlers = handlers

    def repair(
        self,
        signature: FailureSignature,
        template: TraceEvent,
        context: Optional[dict] = None,
    ) -> RepairOutcome:
        context = context or {}

        # --- Emit classification event ---
        events: list[TraceEvent] = [TraceEvent(
            run_id=template.run_id,
            harness_id=template.harness_id,
            event_index=template.event_index + 1,
            turn_index=template.turn_index,
            loop_step=template.loop_step,
            last_tool_called=template.last_tool_called,
            event_type=EventType.FAILURE_CLASSIFIED,
            budget_consumed_cents=template.budget_consumed_cents,
            failure_signature=signature.signature_id,
            verification_detail=signature.detail,
        )]

        candidates = self.library.candidates_for(signature.signature_id)
        if not candidates:
            events.append(self._emit(
                template,
                EventType.REPAIR_FAILED,
                failure_signature=signature.signature_id,
                repair_action=None,
                error="No candidate repair actions for signature.",
            ))
            return RepairOutcome(
                attempted=False,
                action_id=None,
                succeeded=False,
                events=events,
                detail="No candidate actions.",
            )

        # --- Try candidates in order ---
        for action in candidates:
            handler = self.handlers.get(action.action_type)
            if not handler:
                continue

            events.append(self._emit(
                template,
                EventType.REPAIR_ATTEMPTED,
                failure_signature=signature.signature_id,
                repair_action=action.action_id,
            ))

            try:
                succeeded, detail = handler(action, context)
            except Exception as e:
                succeeded, detail = False, f"Handler raised: {e}"

            self.library.record_attempt(
                signature.signature_id, action.action_id, succeeded
            )

            if succeeded:
                events.append(self._emit(
                    template,
                    EventType.REPAIR_SUCCEEDED,
                    failure_signature=signature.signature_id,
                    repair_action=action.action_id,
                ))
                return RepairOutcome(
                    attempted=True,
                    action_id=action.action_id,
                    succeeded=True,
                    events=events,
                    detail=detail,
                )
            else:
                events.append(self._emit(
                    template,
                    EventType.REPAIR_FAILED,
                    failure_signature=signature.signature_id,
                    repair_action=action.action_id,
                    error=detail,
                ))

        return RepairOutcome(
            attempted=True,
            action_id=None,
            succeeded=False,
            events=events,
            detail="All candidate actions failed.",
        )

    def _emit(
        self,
        template: TraceEvent,
        event_type: EventType,
        failure_signature: Optional[str] = None,
        repair_action: Optional[str] = None,
        error: Optional[str] = None,
    ) -> TraceEvent:
        return TraceEvent(
            run_id=template.run_id,
            harness_id=template.harness_id,
            event_index=template.event_index + 2 + int(uuid.uuid4().int % 1000),
            turn_index=template.turn_index,
            loop_step=template.loop_step,
            last_tool_called=template.last_tool_called,
            event_type=event_type,
            budget_consumed_cents=template.budget_consumed_cents,
            failure_signature=failure_signature,
            repair_action=repair_action,
            error=error,
        )