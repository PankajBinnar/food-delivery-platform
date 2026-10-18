
import logging
import time

from sqlalchemy import text

from app.database import SessionLocal
from app.kafka_events import publish_order_created

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3
BATCH_SIZE = 20


def publish_pending_events():
    # Read a batch of pending events.
    with SessionLocal() as db:
        events = db.execute(
            text("""
                SELECT id, event_type, payload
                FROM outbox_events
                WHERE published_at IS NULL
                ORDER BY id
                LIMIT :batch_size
            """),
            {"batch_size": BATCH_SIZE},
        ).mappings().all()

    for event in events:
        event_id = event["id"]

        try:
            if event["event_type"] != "order_created":
                raise ValueError(
                    f"Unsupported outbox event type: "
                    f"{event['event_type']}"
                )

            # Send the event and wait for Kafka acknowledgement.
            publish_order_created(dict(event["payload"]))

            # Mark it published only after Kafka acknowledges it.
            with SessionLocal() as db:
                with db.begin():
                    db.execute(
                        text("""
                            UPDATE outbox_events
                            SET published_at = CURRENT_TIMESTAMP,
                                attempts = attempts + 1,
                                last_error = NULL
                            WHERE id = :event_id
                              AND published_at IS NULL
                        """),
                        {"event_id": event_id},
                    )

            logger.info(
                "Outbox event %s published successfully",
                event_id,
            )

        except Exception as exc:
            logger.exception(
                "Failed to publish outbox event %s",
                event_id,
            )

            # Leave the event pending so it can be retried.
            with SessionLocal() as db:
                with db.begin():
                    db.execute(
                        text("""
                            UPDATE outbox_events
                            SET attempts = attempts + 1,
                                last_error = :error
                            WHERE id = :event_id
                              AND published_at IS NULL
                        """),
                        {
                            "event_id": event_id,
                            "error": str(exc)[:2000],
                        },
                    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    logger.info("Outbox publisher started")

    try:
        while True:
            publish_pending_events()
            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info("Outbox publisher stopped")


if __name__ == "__main__":
    main()
