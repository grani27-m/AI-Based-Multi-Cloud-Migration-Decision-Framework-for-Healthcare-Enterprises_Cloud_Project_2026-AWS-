"""Tanmay: the AWS Lambda wrapper runs the same decision engine (tested locally, not on AWS)."""

import json

from infra.aws.lambda_decision.handler import lambda_handler


def test_direct_invocation():
    r = lambda_handler(
        {"device_id": "ECG-101", "criticality": 9.5, "predicted_latency_ms": 210.5, "cloud_cost_index": 0.4}, None
    )
    assert r["destination"] == "EDGE" and r["reason"] == "override_critical_patient"


def test_api_gateway_proxy_event():
    ev = {
        "body": json.dumps(
            {"device_id": "ECG-102", "criticality": 0.9, "predicted_latency_ms": 33.8, "cloud_cost_index": 0.2}
        )
    }
    r = lambda_handler(ev, None)
    assert r["statusCode"] == 200 and json.loads(r["body"])["destination"] == "CLOUD"


def test_invalid_input_returns_422():
    r = lambda_handler({"body": json.dumps({"device_id": "X", "criticality": 42, "cloud_cost_index": 0.2})}, None)
    assert r["statusCode"] == 422
