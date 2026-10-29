"""Prometheus metrics (optional dependency).  Owner: Rani Gupta"""
from __future__ import annotations

try:
    from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    AVAILABLE = True
except ImportError:  # pragma: no cover
    AVAILABLE = False


class Metrics:
    def __init__(self):
        self.enabled = AVAILABLE
        if not AVAILABLE:
            return
        self.registry = CollectorRegistry()
        self.requests = Histogram("hcf_http_request_seconds", "HTTP request latency", ["method", "path", "status"],
                                  registry=self.registry)
        self.events = Counter("hcf_events_total", "Processed telemetry events",
                              ["source", "destination", "reason", "status"], registry=self.registry)
        self.prediction_method = Counter("hcf_predictions_total", "Predictions by method", ["method"],
                                         registry=self.registry)

    def observe_request(self, method: str, path: str, status: int, seconds: float) -> None:
        if self.enabled:
            self.requests.labels(method, path, str(status)).observe(seconds)

    def observe_event(self, r: dict) -> None:
        if not self.enabled or r.get("duplicate"):
            return
        d = r.get("decision") or {}
        self.events.labels(r["source"], d.get("destination", "none"), d.get("reason", "none"), r["status"]).inc()
        if r.get("prediction"):
            self.prediction_method.labels(r["prediction"]["method"]).inc()

    def render(self) -> tuple[bytes, str]:
        if not self.enabled:
            return b"# prometheus_client not installed\n", "text/plain"
        return generate_latest(self.registry), CONTENT_TYPE_LATEST
