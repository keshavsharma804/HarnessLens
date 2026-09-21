"""Verify the OTel normalizer converts schema events without losing signal."""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry import trace

from adapters.dummy_adapter import DummyHarness
from app.otel_normalizer import emit_run


def test_normalizer_emits_spans():
    """Every TraceEvent should produce a span with the routing signal intact."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    harness = DummyHarness()
    events = harness.run("test task")
    emit_run(events)

    spans = exporter.get_finished_spans()
    assert len(spans) == len(events)

    tool_spans = [s for s in spans if s.name == "tool.called"]
    assert len(tool_spans) == 3

    # The routing signal must survive the conversion.
    first_tool = tool_spans[0]
    assert first_tool.attributes["loop_step"] == 1
    assert first_tool.attributes["last_tool_called"] == "read_file"
    assert first_tool.attributes["harness_id"] == "dummy"