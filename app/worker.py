import os
import time

from app.db.session import SessionLocal
from app.notifications import NotificationProcessor, notification_provider_from_environment


def run_once() -> int:
    db = SessionLocal()
    try:
        processor = NotificationProcessor(notification_provider_from_environment())
        return processor.process_available(db)
    finally:
        db.close()


def main() -> None:
    poll_seconds = int(os.getenv("NOTIFICATION_WORKER_POLL_SECONDS", "10"))
    while True:
        run_once()
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
