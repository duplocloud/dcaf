"""EventPublisher port - interface for publishing domain events."""

from typing import Protocol, runtime_checkable

from ...domain.events import DomainEvent


@runtime_checkable
class EventPublisher(Protocol):
    """
    Port for publishing domain events.

    This protocol defines the interface for publishing domain events
    to external systems (message queues, event stores, etc.).

    Implementations:
        - InMemoryEventPublisher: For testing
        - SQSEventPublisher: For AWS SQS
        - KafkaEventPublisher: For Kafka

    Example:
        class LoggingEventPublisher(EventPublisher):
            def publish(self, event: DomainEvent) -> None:
                logger.info(f"Event: {event.event_type}", extra={"event": event})

            def publish_all(self, events: List[DomainEvent]) -> None:
                for event in events:
                    self.publish(event)
    """

    def publish(self, event: DomainEvent) -> None:
        """
        Publish a single domain event.

        Args:
            event: The domain event to publish
        """
        ...

    def publish_all(self, events: list[DomainEvent]) -> None:
        """
        Publish multiple domain events.

        Events should be published in order.

        Args:
            events: List of domain events to publish
        """
        ...
