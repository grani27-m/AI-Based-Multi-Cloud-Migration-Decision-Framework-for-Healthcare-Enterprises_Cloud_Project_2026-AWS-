"""
Optional MQTT -> REST bridge (Rani). Subscribes to device topics and forwards every message to
POST /api/v1/events, so MQTT data goes through exactly the same validation, pipeline and audit as REST.

    MQTT_HOST=localhost DEVICE_PASSWORD=... python -m scripts.mqtt_bridge
    topic: hcf/devices/<device_id>/events   payload: the EventIn JSON (see integration/API_CONTRACT.md)

Messages the API rejects are appended to runtime/mqtt_dead_letters.jsonl (nothing is dropped silently).
Requires: pip install paho-mqtt. The AWS target for this component is AWS IoT Core.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import httpx

log = logging.getLogger("mqtt_bridge")
DEAD = Path(os.environ.get("RUNTIME_DIR", "runtime")) / "mqtt_dead_letters.jsonl"


class Forwarder:
    def __init__(self, api: str, user: str, password: str, client: httpx.Client | None = None):
        self.api, self.user, self.password = api, user, password
        self.http = client or httpx.Client(base_url=api, timeout=30)
        self.token = None

    def _login(self):
        r = self.http.post("/api/v1/auth/login", json={"username": self.user, "password": self.password})
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def handle(self, topic: str, raw: bytes) -> int:
        try:
            body = json.loads(raw)
        except ValueError:
            return self._dead(topic, raw, "invalid JSON")
        parts = topic.split("/")
        if len(parts) >= 3 and body.get("device_id") not in (None, parts[2]):
            return self._dead(topic, raw, "device_id does not match topic")
        body.setdefault("source", "live")
        for _ in range(2):
            if not self.token:
                self._login()
            r = self.http.post("/api/v1/events", json=body, headers={"Authorization": f"Bearer {self.token}"})
            if r.status_code == 401:
                self.token = None
                continue
            if r.status_code in (200, 201):
                return r.status_code
            return self._dead(topic, raw, f"HTTP {r.status_code}: {r.text[:200]}")
        return self._dead(topic, raw, "authentication failed")

    def _dead(self, topic, raw, err) -> int:
        DEAD.parent.mkdir(parents=True, exist_ok=True)
        with DEAD.open("a") as f:
            f.write(
                json.dumps(
                    {"ts": time.time(), "topic": topic, "payload": raw.decode(errors="replace")[:5000], "error": err}
                )
                + "\n"
            )
        log.warning("dead-lettered message on %s: %s", topic, err)
        return 0


def main() -> int:
    import paho.mqtt.client as mqtt

    logging.basicConfig(level=logging.INFO)
    fw = Forwarder(
        os.environ.get("API_URL", "http://127.0.0.1:8000"),
        os.environ.get("STREAM_USER", "sim-device"),
        os.environ["DEVICE_PASSWORD"],
    )
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=os.environ.get("MQTT_CLIENT_ID", "hcf-bridge"))
    c.on_connect = lambda cl, u, f, rc, p=None: cl.subscribe(
        os.environ.get("MQTT_TOPIC", "hcf/devices/+/events"), qos=1
    )
    c.on_message = lambda cl, u, m: fw.handle(m.topic, m.payload)
    c.reconnect_delay_set(1, 60)
    c.connect(os.environ.get("MQTT_HOST", "localhost"), int(os.environ.get("MQTT_PORT", 1883)))
    c.loop_forever(retry_first_connection=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
