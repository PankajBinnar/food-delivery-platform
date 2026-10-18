
import json
import logging
import os

from kafka import KafkaConsumer
from sqlalchemy import text

from app.database import SessionLocal


# --------------------------------------------------
# Logging configuration
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Kafka consumer configuration
# --------------------------------------------------

consumer = KafkaConsumer(
    "orders",
    bootstrap_servers=os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS",
        "localhost:9092",
    ),
    group_id="food-delivery-order-workers",
    auto_offset_reset="earliest",
    enable_auto_commit=False,
    value_deserializer=lambda value: json.loads(
        value.decode("utf-8")
    ),
)


# --------------------------------------------------
# Process order-created events
# --------------------------------------------------

def process_order_event(event: dict) -> bool:
    """
    Process an order-created event.

    Returns:
        True  - event was newly processed.
        False - event was already processed.

    The event record and restaurant notification are
    committed together in a single database transaction.
    """

    if not isinstance(event, dict):
        raise ValueError("Kafka event must be a JSON object")

    event_type = event.get("event_type")
    order_id = event.get("order_id")

    if event_type != "order_created":
        raise ValueError(f"Unsupported event type: {event_type}")

    if not isinstance(order_id, int) or isinstance(order_id, bool):
        raise ValueError("Event must contain a valid integer order_id")

    event_key = f"{event_type}:{order_id}"

    with SessionLocal() as db:
        with db.begin():

            # 1. Verify the order exists and retrieve trusted details.
            order = db.execute(
                text("""
                    SELECT id, restaurant_id, status, total_amount
                    FROM orders
                    WHERE id = :order_id
                """),
                {"order_id": order_id},
            ).mappings().first()

            if order is None:
                raise ValueError(
                    f"Order {order_id} does not exist"
                )

            # 2. Claim the event. The primary key prevents duplicates.
            inserted_key = db.execute(
                text("""
                    INSERT INTO processed_events (
                        event_key,
                        event_type,
                        order_id
                    )
                    VALUES (
                        :event_key,
                        :event_type,
                        :order_id
                    )
                    ON CONFLICT (event_key) DO NOTHING
                    RETURNING event_key
                """),
                {
                    "event_key": event_key,
                    "event_type": event_type,
                    "order_id": order_id,
                },
            ).scalar_one_or_none()

            # 3. Ensure the notification exists even if an earlier
            # version of the consumer recorded the event without it.
            db.execute(
                text("""
                    INSERT INTO restaurant_notifications (
                        order_id,
                        restaurant_id,
                        message,
                        status
                    )
                    VALUES (
                        :order_id,
                        :restaurant_id,
                        :message,
                        'PENDING'
                    )
                    ON CONFLICT (order_id) DO NOTHING
                """),
                {
                    "order_id": order["id"],
                    "restaurant_id": order["restaurant_id"],
                    "message": (
                        f"New order #{order['id']} received. "
                        f"Total: {order['total_amount']}"
                    ),
                },
            )

            if inserted_key is None:
                logger.info(
                    "Duplicate event acknowledged: %s",
                    event_key,
                )
                return False

            logger.info(
                "Created restaurant notification for order %s",
                order_id,
            )

    # The transaction has committed successfully.
    return True


# --------------------------------------------------
# Consume Kafka messages
# --------------------------------------------------

def main():
    logger.info(
        "Order consumer started. Waiting for messages..."
    )

    try:
        for message in consumer:
            event = message.value

            try:
                processed = process_order_event(event)

                # Commit only after database processing succeeds.
                consumer.commit()

                if processed:
                    logger.info(
                        "Successfully processed event: %s",
                        event,
                    )
                else:
                    logger.info(
                        "Duplicate event skipped safely: %s",
                        event,
                    )

                logger.info(
                    "Offset committed: topic=%s partition=%s offset=%s",
                    message.topic,
                    message.partition,
                    message.offset,
                )

            except Exception:
                logger.exception(
                    "Event processing failed. "
                    "Kafka offset was not committed."
                )

                # Stop instead of skipping the failed message.
                # Retry/recovery handling can be added later.
                break

    except KeyboardInterrupt:
        logger.info("Consumer stopped by user.")

    finally:
        consumer.close()
        logger.info("Kafka consumer closed.")


# --------------------------------------------------
# Application entry point
# --------------------------------------------------

if __name__ == "__main__":
    main()
