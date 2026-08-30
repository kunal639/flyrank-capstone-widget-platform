# app/repositories/submission.py
import uuid
from typing import Any, Optional
from sqlalchemy.orm import Session
from app.models.submission import Submission
from app.models.submission_field_value import SubmissionFieldValue
from app.models.notification_outbox import NotificationOutbox

class SubmissionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, submission_id: uuid.UUID) -> Optional[Submission]:
        return (
            self.db.query(Submission)
            .filter(Submission.submission_id == submission_id)
            .first()
        )

    def get_by_idempotency_key(
        self, widget_id: uuid.UUID, idempotency_key: str
    ) -> Optional[Submission]:
        return (
            self.db.query(Submission)
            .filter(
                Submission.widget_id == widget_id,
                Submission.idempotency_key == idempotency_key,
            )
            .first()
        )

    def create_submission_with_values(
        self,
        widget_id: uuid.UUID,
        idempotency_key: str,
        field_values: list[dict[str, Any]],
        geo_data: Optional[dict[str, Any]] = None,
        enqueue_notification: bool = True
    ) -> Submission:
        """
        Creates Submission + Field Values + NotificationOutbox within the current transaction.
        Uses db.flush() so entities get IDs without committing prematurely.
        """
        geo_data = geo_data or {}
        submission = Submission(
            widget_id=widget_id,
            idempotency_key=idempotency_key,
            country=geo_data.get("country"),
            city=geo_data.get("city"),
            region=geo_data.get("region"),
            latitude=geo_data.get("latitude"),
            longitude=geo_data.get("longitude"),
        )
        self.db.add(submission)
        self.db.flush()

        for item in field_values:
            val = SubmissionFieldValue(
                submission_id=submission.submission_id,
                widget_field_id=item["widget_field_id"],
                value_text=item.get("value_text"),
                value_number=item.get("value_number"),
                value_boolean=item.get("value_boolean"),
            )
            self.db.add(val)

        if enqueue_notification:
            outbox_entry = NotificationOutbox(
                submission_id=submission.submission_id,
                status="pending"
            )
            self.db.add(outbox_entry)

        self.db.flush()
        return submission