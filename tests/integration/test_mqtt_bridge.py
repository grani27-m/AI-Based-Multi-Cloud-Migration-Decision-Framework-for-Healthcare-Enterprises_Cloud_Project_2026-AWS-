"""Rani: MQTT bridge forwards valid messages through the real API and dead-letters bad ones (no broker needed)."""

import json

import backend  # noqa: F401
from scripts import mqtt_bridge
from tests.conftest import event


def test_bridge_forwards_and_dead_letters(client, tmp_path, monkeypatch):
    monkeypatch.setattr(mqtt_bridge, "DEAD", tmp_path / "dead.jsonl")
    fw = mqtt_bridge.Forwarder("http://testserver", "dev1", "correct-horse-battery", client=client)
    good = event("mqtt-evt-1", device="MQTT-DEV-1")
    good.pop("source")
    assert fw.handle("hcf/devices/MQTT-DEV-1/events", json.dumps(good).encode()) == 201
    assert fw.handle("hcf/devices/MQTT-DEV-1/events", b"{not json") == 0
    assert fw.handle("hcf/devices/OTHER/events", json.dumps(good).encode()) == 0
    bad = {**good, "event_id": "mqtt-evt-2", "criticality": 99}
    assert fw.handle("hcf/devices/MQTT-DEV-1/events", json.dumps(bad).encode()) == 0
    lines = (tmp_path / "dead.jsonl").read_text().splitlines()
    assert len(lines) == 3
