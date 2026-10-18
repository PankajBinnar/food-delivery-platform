import json
import logging
import os

from kafka import KafkaProducer

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:9092",
)

_producer = None


def get_producer():
    global _producer

    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            acks="all",
            retries=5,
        )

    return _producer


def publish_order_created(order_event: dict):
    producer = get_producer()

    future = producer.send("orders", value=order_event)
    metadata = future.get(timeout=10)

    logger.info(
        "Published order event: topic=%s partition=%s offset=%s",
        metadata.topic,
        metadata.partition,
        metadata.offset,
    )

    return {
        "topic": metadata.topic,
        "partition": metadata.partition,
        "offset": metadata.offset,
    }
