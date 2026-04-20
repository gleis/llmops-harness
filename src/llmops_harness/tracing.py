"""OpenTelemetry setup. One call to configure(), then `tracer` is usable."""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .settings import settings

_configured = False
tracer = trace.get_tracer("llmops_harness")


def configure() -> None:
    """Wire OTLP exporter once. Safe to call multiple times."""
    global _configured, tracer
    if _configured:
        return

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("llmops_harness")
    _configured = True
