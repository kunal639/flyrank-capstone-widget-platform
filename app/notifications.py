import json
import os
from datetime import datetime, timedelta, timezone
from typing import Protocol
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session, joinedload

from app.models.notification_outbox import NotificationOutbox
from app.models.submission import Submission


class NotificationProvider(Protocol):
    def send(self, submission: Submission) -> None: ...


class DisabledNotificationProvider:
    def send(self, submission: Submission) -> None:
        raise RuntimeError("Notification delivery is not configured")


class WebhookNotificationProvider:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, submission: Submission) -> None:
        payload = json.dumps(
            {
                "submission_id": str(submission.submission_id),
                "widget_id": str(submission.widget_id),
                "created_at": submission.created_at.isoformat(),
            }
        ).encode()
        request = Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=3) as response:  # noqa: S310 - configured URL
            if not 200 <= response.status < 300:
                raise RuntimeError("Notification webhook returned a non-success status")


def notification_provider_from_environment() -> NotificationProvider:
    webhook_url = os.getenv("NOTIFICATION_WEBHOOK_URL")
    if webhook_url:
        return WebhookNotificationProvider(webhook_url)
    return DisabledNotificationProvider()


class NotificationProcessor:
    def __init__(
        self,
        provider: NotificationProvider,
        max_attempts: int = 3,
        retry_base_seconds: int = 60,
    ):
        self.provider = provider
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds

    def process_available(self, db: Session, batch_size: int = 100) -> int:
        now = datetime.now(timezone.utc)
        outbox_entries = (
            db.query(NotificationOutbox)
            .options(joinedload(NotificationOutbox.submission))
            .filter(
                NotificationOutbox.status.in_(("pending", "retry")),
                NotificationOutbox.available_at <= now,
            )
            .order_by(NotificationOutbox.available_at)
            .limit(batch_size)
            .all()
        )

        for outbox_entry in outbox_entries:
            submission = outbox_entry.submission
            outbox_entry.status = "processing"
            try:
                self.provider.send(submission)
            except Exception as error:
                attempts = outbox_entry.attempts + 1
                outbox_entry.attempts = attempts
                outbox_entry.last_error = type(error).__name__
                submission.notification_attempts = attempts
                if attempts >= self.max_attempts:
                    outbox_entry.status = "failed"
                    outbox_entry.processed_at = now
                    submission.notification_status = "failed"
                else:
                    outbox_entry.status = "retry"
                    outbox_entry.available_at = now + timedelta(
                        seconds=self.retry_base_seconds * (2 ** (attempts - 1))
                    )
                    submission.notification_status = "pending"
            else:
                outbox_entry.status = "succeeded"
                outbox_entry.attempts += 1
                outbox_entry.last_error = None
                outbox_entry.processed_at = now
                submission.notification_status = "succeeded"
                submission.notification_attempts = outbox_entry.attempts

        db.commit()
        return len(outbox_entries)
