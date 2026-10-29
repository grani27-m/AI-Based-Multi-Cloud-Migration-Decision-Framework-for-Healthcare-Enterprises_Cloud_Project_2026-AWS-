"""
backend/services/alerts.py  —  Owner: Rani Gupta
=================================================
Alert life-cycle with an explicit delivery log, fixing the old defect where
"alerts sent" was simply the number of emergency overrides.

    triggered            alert row created by the pipeline
    -> not_notified      severity not in ALERT_NOTIFY_SEVERITIES (recorded only)
    -> not_configured    no channel configured (every channel logged as "skipped")
    -> delivered         every configured channel succeeded
    -> partially_delivered / failed

Channels (all optional, credentials only from environment):
    telegram  Bot API sendMessage          TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    email     SMTP + STARTTLS              SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, ALERT_EMAIL_TO
    webhook   JSON POST (Slack/Discord/…)  ALERT_WEBHOOK_URL
    aws-sns   SNS Publish                  SNS_TOPIC_ARN (+ AWS credentials)

Each channel gets up to 3 attempts with a 10 s timeout; every attempt is an
alert_deliveries row. Messages contain the device ID, criticality and latency only
(no patient identity). Error details are sanitised so tokens never reach the DB.
"""

from __future__ import annotations

import logging
import smtplib
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from types import SimpleNamespace
from typing import Callable

import httpx

from backend.audit import write_audit
from backend.config import Settings
from backend.models import Alert, AlertDelivery

log = logging.getLogger("alerts")
MAX_ATTEMPTS = 3


class Channel:
    name = "base"

    def configured(self) -> bool:
        raise NotImplementedError

    def send(self, alert: Alert) -> str:
        """Return a short sanitised detail string on success, raise on failure."""
        raise NotImplementedError


def _sanitise(msg: str, secrets_: list[str]) -> str:
    for s in secrets_:
        if s:
            msg = msg.replace(s, "***")
    return msg[:300]


class TelegramChannel(Channel):
    name = "telegram"

    def __init__(self, s: Settings):
        self.token, self.chat = s.telegram_bot_token, s.telegram_chat_id

    def configured(self):
        return bool(self.token and self.chat)

    def send(self, alert):
        r = httpx.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={"chat_id": self.chat, "text": alert.message},
            timeout=10,
        )
        if r.status_code != 200 or not r.json().get("ok"):
            raise RuntimeError(f"telegram HTTP {r.status_code}")
        return f"telegram message_id={r.json()['result'].get('message_id')}"


class EmailChannel(Channel):
    name = "email"

    def __init__(self, s: Settings):
        self.s = s

    def configured(self):
        s = self.s
        return bool(s.smtp_host and s.smtp_username and s.smtp_password and s.alert_email_to)

    def send(self, alert):
        s = self.s
        msg = MIMEText(alert.message)
        msg["Subject"] = f"[{alert.severity}] {alert.kind} - device {alert.device_id}"
        msg["From"] = s.smtp_from or s.smtp_username
        msg["To"] = s.alert_email_to
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as srv:
            srv.starttls()
            srv.login(s.smtp_username, s.smtp_password)
            refused = srv.sendmail(msg["From"], [s.alert_email_to], msg.as_string())
        if refused:
            raise RuntimeError("recipient refused")
        return "smtp accepted"


class WebhookChannel(Channel):
    name = "webhook"

    def __init__(self, s: Settings):
        self.url = s.alert_webhook_url

    def configured(self):
        return bool(self.url)

    def send(self, alert):
        r = httpx.post(
            self.url,
            json={
                "text": alert.message,
                "content": alert.message,
                "severity": alert.severity,
                "device_id": alert.device_id,
            },
            timeout=10,
        )
        if r.status_code >= 300:
            raise RuntimeError(f"webhook HTTP {r.status_code}")
        return f"webhook HTTP {r.status_code}"


class SNSChannel(Channel):
    """Amazon SNS publish (only when SNS_TOPIC_ARN is set and AWS credentials exist)."""

    name = "aws-sns"

    def __init__(self, s: Settings):
        import os

        self.topic = os.environ.get("SNS_TOPIC_ARN", "")

    def configured(self):
        return bool(self.topic)

    def send(self, alert):
        import boto3

        r = boto3.client("sns").publish(
            TopicArn=self.topic, Subject=f"[{alert.severity}] {alert.kind}"[:100], Message=alert.message
        )
        return f"sns MessageId={r.get('MessageId')}"


def default_channels(s: Settings) -> list[Channel]:
    return [TelegramChannel(s), EmailChannel(s), WebhookChannel(s), SNSChannel(s)]


def dispatch_alert(
    session_factory: Callable,
    settings: Settings,
    alert_id: int,
    channels: list[Channel] | None = None,
    backoff_s: float = 1.0,
) -> str:
    """Deliver one alert through every configured channel and persist every attempt.

    Three short phases so that no database transaction is open during network I/O:
      1. claim the alert (triggered -> dispatching) - makes dispatch idempotent;
      2. call the providers (no DB session held);
      3. store every attempt, the final status and an audit entry in one transaction.
    """
    channels = channels if channels is not None else default_channels(settings)
    secrets_ = [settings.telegram_bot_token, settings.smtp_password, settings.alert_webhook_url]
    with session_factory() as db:  # phase 1
        alert = db.get(Alert, alert_id)
        if alert is None:
            return "missing"
        if alert.status != "triggered":
            return alert.status
        notify = alert.severity in settings.alert_notify_severities
        alert.status = "dispatching" if notify else "not_notified"
        snapshot = SimpleNamespace(
            id=alert.id, message=alert.message, severity=alert.severity, kind=alert.kind, device_id=alert.device_id
        )
        if not notify:
            write_audit(
                db,
                "alert-service",
                "alert_dispatched",
                f"alert/{alert.id}",
                {"status": "not_notified", "severity": alert.severity, "kind": alert.kind},
            )
            return "not_notified"

    attempts: list[dict] = []  # phase 2 - network calls only
    outcomes: list[bool] = []
    for ch in channels:
        if not ch.configured():
            attempts.append(
                dict(channel=ch.name, attempt=0, status="skipped", detail="channel not configured", latency_ms=0.0)
            )
            continue
        ok = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t0 = time.perf_counter()
            try:
                detail = ch.send(snapshot)
                ok = True
                attempts.append(
                    dict(
                        channel=ch.name,
                        attempt=attempt,
                        status="sent",
                        detail=detail,
                        latency_ms=(time.perf_counter() - t0) * 1000,
                    )
                )
                break
            except Exception as exc:
                attempts.append(
                    dict(
                        channel=ch.name,
                        attempt=attempt,
                        status="failed",
                        detail=_sanitise(f"{type(exc).__name__}: {exc}", secrets_),
                        latency_ms=(time.perf_counter() - t0) * 1000,
                    )
                )
                if attempt < MAX_ATTEMPTS:
                    time.sleep(backoff_s * attempt)
        outcomes.append(ok)

    if not outcomes:
        status = "not_configured"
    elif all(outcomes):
        status = "delivered"
    elif any(outcomes):
        status = "partially_delivered"
    else:
        status = "failed"
    with session_factory() as db:  # phase 3
        alert = db.get(Alert, alert_id)
        for a in attempts:
            db.add(AlertDelivery(alert_id=alert_id, **a))
        alert.status = status
        if status in ("delivered", "partially_delivered"):
            alert.delivered_at = datetime.now(timezone.utc)
        write_audit(
            db,
            "alert-service",
            "alert_dispatched",
            f"alert/{alert_id}",
            {
                "status": status,
                "severity": alert.severity,
                "kind": alert.kind,
                "channels": sorted({a["channel"] for a in attempts if a["status"] == "sent"}),
            },
        )
    log.info("alert %s -> %s", alert_id, status)
    return status
