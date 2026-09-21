"""Console exporter for local dev. Prints spans as JSON to stdout."""
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

console_exporter = ConsoleSpanExporter()