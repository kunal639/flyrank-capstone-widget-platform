import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.notification_outbox import NotificationOutbox
from app.models.submission import Submission
from app.models.widget import Widget
from app.models.widget_type import WidgetType
from app.notifications import NotificationProcessor


class SuccessfulProvider:
    def __init__(self):
        self.submission_ids = []

    def send(self, submission):
        self.submission_ids.append(submission.submission_id)


class FailingProvider:
    def send(self, submission):
        raise ConnectionError("provider unavailable")


@pytest.fixture
def db():
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def notification_entry(db):
    widget_type = WidgetType(name=f"notification_{uuid.uuid4().hex[:8]}")
    widget = Widget(title="Notification widget", widget_type=widget_type, allowed_origins=[])
    submission = Submission(widget=widget, idempotency_key=uuid.uuid4().hex)
    outbox = NotificationOutbox(
        submission=submission,
        available_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    db.add(outbox)
    db.commit()
    return submission, outbox


def test_notification_processor_marks_successful_delivery(db):
    submission, outbox = notification_entry(db)
    provider = SuccessfulProvider()

    assert NotificationProcessor(provider).process_available(db, batch_size=1) == 1

    db.refresh(submission)
    db.refresh(outbox)
    assert provider.submission_ids == [submission.submission_id]
    assert (submission.notification_status, submission.notification_attempts) == (
        "succeeded",
        1,
    )
    assert (outbox.status, outbox.attempts, outbox.last_error) == ("succeeded", 1, None)
    assert outbox.processed_at is not None


def test_notification_processor_retries_then_marks_final_failure(db):
    submission, outbox = notification_entry(db)
    processor = NotificationProcessor(FailingProvider(), max_attempts=3, retry_base_seconds=1)

    assert processor.process_available(db, batch_size=1) == 1
    db.refresh(submission)
    db.refresh(outbox)
    assert (outbox.status, outbox.attempts, outbox.last_error) == (
        "retry",
        1,
        "ConnectionError",
    )
    assert submission.notification_status == "pending"
    assert submission.notification_attempts == 1
    assert outbox.available_at > datetime.now(timezone.utc) - timedelta(seconds=1)

    for expected_attempt in (2, 3):
        outbox.available_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        db.commit()
        assert processor.process_available(db, batch_size=1) == 1
        db.refresh(submission)
        db.refresh(outbox)
        assert outbox.attempts == expected_attempt

    assert outbox.status == "failed"
    assert outbox.processed_at is not None
    assert submission.notification_status == "failed"
    assert submission.notification_attempts == 3
    assert db.get(Submission, submission.submission_id) is not None
