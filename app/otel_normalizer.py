"""
Converts unified TraceEvents into OpenTelemetry spans.

Why OTel instead of custom logs:
- Neutral contract: any harness can emit OTel; we don't force our schema on them.
- Standard exporters: Grafana, Jaeger, Honeycomb, Datadog all consume OTel.
- Future-proof: if a harness emits OTel natively, we just read its spans directly.

Design decision: we emit one span per TraceEvent, with attributes matching
our schema fields. Parent/child relationships link a run's spans together.
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)
from opentelemetry.sdk.resources import Resource

from app.schema import TraceEvent, EventType


_tracer_provider = None
_tracer = None


def _ensure_tracer(exporter: SpanExporter | None = None):
    """Lazy-init the tracer with a resource identifying our service."""
    global _tracer_provider, _tracer

    if _tracer is not None:
        return _tracer

    resource = Resource.create({
        "service.name": "harness-control-plane",
        "service.version": "0.1.0",
    })
    _tracer_provider = TracerProvider(resource=resource)

    if exporter is not None:
        _tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))

    trace.set_tracer_provider(_tracer_provider)
    _tracer = trace.get_tracer("harness-control-plane.normalizer")
    return _tracer


# Map our EventType to OTel span kinds for downstream consumers.
_EVENT_TYPE_TO_SPAN_NAME = {
    EventType.RUN_STARTED: "run.started",
    EventType.STEP_STARTED: "step.started",
    EventType.TOOL_CALLED: "tool.called",
    EventType.TOOL_RESULT: "tool.result",
    EventType.VERIFICATION_CHECKED: "verification.checked",
    EventType.RUN_COMPLETED: "run.completed",
    EventType.RUN_FAILED: "run.failed",
    EventType.BUDGET_WARNING: "budget.warning",
}


def emit_span(event: TraceEvent, exporter: SpanExporter | None = None):
    """
    Convert one TraceEvent into one OTel span.

    Every schema field becomes a span attribute, so downstream tools
    (Grafana, Jaeger) can filter/aggregate without knowing our schema.
    """
    tracer = _ensure_tracer(exporter)

    span_name = _EVENT_TYPE_TO_SPAN_NAME.get(
        EventType(event.event_type), f"event.{event.event_type}"
    )

    with tracer.start_as_current_span(span_name) as span:
        # --- Identity ---
        span.set_attribute("run_id", event.run_id)
        span.set_attribute("harness_id", event.harness_id)
        span.set_attribute("event_index", event.event_index)
        span.set_attribute("turn_index", event.turn_index)

        # --- THE routing signal ---
        span.set_attribute("loop_step", event.loop_step)
        if event.last_tool_called:
            span.set_attribute("last_tool_called", event.last_tool_called)

        # --- Timing & cost ---
        if event.latency_ms is not None:
            span.set_attribute("latency_ms", event.latency_ms)
        if event.input_tokens is not None:
            span.set_attribute("input_tokens", event.input_tokens)
        if event.output_tokens is not None:
            span.set_attribute("output_tokens", event.output_tokens)
        if event.cost_cents is not None:
            span.set_attribute("cost_cents", event.cost_cents)
        span.set_attribute("budget_consumed_cents", event.budget_consumed_cents)

        # --- Verification ---
        span.set_attribute("verification_status", event.verification_status)

        # --- Error ---
        if event.error:
            span.set_attribute("error", event.error)
            span.set_status(trace.Status(trace.StatusCode.ERROR, event.error))

        return span


def emit_run(events: list[TraceEvent], exporter: SpanExporter | None = None):
    """Emit all events from a single run. Returns the list of spans created."""
    return [emit_span(e, exporter) for e in events]