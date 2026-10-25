import json
import logging
import traceback
from datetime import datetime, timezone
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from prometheus_client import Counter, Gauge, Histogram
from relayops.core.config import settings

accepted = Counter("relayops_events_accepted", "Committed events")
backpressure = Counter("relayops_backpressure", "Rejected ingestion due to queue capacity")
attempted = Counter("relayops_deliveries_attempted", "HTTP dispatches", ["region"])
succeeded = Counter("relayops_deliveries_succeeded", "Acknowledged deliveries", ["region"])
failed = Counter("relayops_deliveries_failed", "Failed attempts", ["region"])
retries = Counter("relayops_retries", "Scheduled retries", ["region"])
dead = Counter("relayops_dead_letters", "Exhausted deliveries", ["region"])
queue = Gauge("relayops_queue_depth", "Current active jobs")
inflight = Gauge("relayops_in_flight", "Leased deliveries")
heartbeat = Gauge("relayops_worker_heartbeat_timestamp", "Last persisted heartbeat", ["region"])
http_duration = Histogram(
    "relayops_http_request_duration_seconds",
    "Outbound HTTP duration",
    ["region"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
e2e_duration = Histogram(
    "relayops_delivery_duration_seconds",
    "Acceptance to success",
    ["region"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
tracer = trace.get_tracer("relayops")


class JSONFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            # Exception messages can contain SQL parameters, credentials or payloads.
            # Keep the type and code locations without serializing values or locals.
            entry["exception_type"] = record.exc_info[0].__name__
            entry["stack"] = [
                {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_tb(record.exc_info[2])
            ]
        return json.dumps(entry)


def setup(service: str):
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    if settings().otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings().otel_exporter_otlp_endpoint))
        )
    trace.set_tracer_provider(provider)
