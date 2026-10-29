"""
AWS Lambda entry point for Tanmay's decision engine (src/decision/*), packaged unchanged.

Accepts either a direct invocation payload or an API Gateway (HTTP API, payload v2) proxy event:
    {"device_id": "ECG-101", "criticality": 9.5, "predicted_latency_ms": 210.5, "cloud_cost_index": 0.4}
Returns the full DecisionResult (destination, reason, scores, weights, explanation).
Pure Python: no layers or third-party packages are needed.
"""

import json
import logging

from src.decision.router import DecisionInput, DecisionInputError, decide

log = logging.getLogger()
log.setLevel(logging.INFO)


def _resp(code, body, proxy):
    return (
        {"statusCode": code, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}
        if proxy
        else body
    )


def lambda_handler(event, context):
    proxy = isinstance(event, dict) and "body" in event
    try:
        body = json.loads(event["body"] or "{}") if proxy else event
        r = decide(
            DecisionInput(
                device_id=str(body.get("device_id", "")),
                criticality=body.get("criticality"),
                predicted_latency_ms=body.get("predicted_latency_ms"),
                cloud_cost_index=body.get("cloud_cost_index"),
            )
        )
        log.info(json.dumps({"device_id": r.device_id, "destination": r.destination, "reason": r.reason}))
        return _resp(200, r.to_dict(), proxy)
    except (DecisionInputError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _resp(422, {"error": str(exc)}, proxy)
