"""
Queue abstraction layer that supports multiple backends
"""

import config  # Load environment variables
import os
import json
import abc
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable

import log


log.configure(os.environ)


class QueueMessage:
    """Represents a queue message"""

    def __init__(self, id: str, content: Dict[Any, Any], receipt_handle: Any = None):
        self.id = id
        self.content = content
        self.receipt_handle = receipt_handle


class QueueInterface(abc.ABC):
    """Abstract base class for queue implementations"""

    @abc.abstractmethod
    def send_message(self, message: Dict[Any, Any]) -> bool:
        """Send a message to the queue"""
        pass

    @abc.abstractmethod
    def receive_message(self, visibility_timeout: int = 300) -> Optional[QueueMessage]:
        """Receive a message from the queue"""
        pass

    @abc.abstractmethod
    def delete_message(self, message: QueueMessage) -> bool:
        """Delete a message from the queue"""
        pass

    @abc.abstractmethod
    def return_message(self, message: QueueMessage) -> bool:
        """Return a message to the queue (make visible again)"""
        pass


class FileQueue(QueueInterface):
    """File-based queue implementation for local development"""

    def __init__(
        self,
        queue_dir: str = "queue",
        logger: logging.Logger = logging.getLogger("queue.FileQueue"),
    ):
        self.queue_dir = queue_dir
        self.logger = logger
        os.makedirs(queue_dir, exist_ok=True)

    def send_message(self, message: Dict[Any, Any]) -> bool:
        """Write a job file to the queue directory"""
        try:
            job_id = f"job-{datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')}.json"
            temp_path = os.path.join(self.queue_dir, f".tmp-{job_id}")
            final_path = os.path.join(self.queue_dir, job_id)

            with open(temp_path, "w") as f:
                json.dump(message, f)
            os.rename(temp_path, final_path)  # Atomic write
            return True
        except Exception:
            self.logger.exception("Error sending message")
            return False

    def receive_message(self, visibility_timeout: int = 300) -> Optional[QueueMessage]:
        """Claim a job from the file system"""
        try:
            for filename in sorted(os.listdir(self.queue_dir)):
                if not filename.startswith("job-") or not filename.endswith(".json"):
                    continue

                job_path = os.path.join(self.queue_dir, filename)
                processing_path = job_path + ".processing"

                try:
                    # Atomic claim via rename
                    os.rename(job_path, processing_path)

                    # Read job
                    with open(processing_path) as f:
                        content = json.load(f)

                    return QueueMessage(
                        id=filename, content=content, receipt_handle=processing_path
                    )
                except (OSError, FileNotFoundError):
                    continue
        except Exception:
            self.logger.exception("Error receiving message")

        return None

    def delete_message(self, message: QueueMessage) -> bool:
        """Remove the processing file"""
        try:
            if os.path.exists(message.receipt_handle):
                os.remove(message.receipt_handle)
            return True
        except Exception:
            self.logger.exception("Error deleting message")
            return False

    def return_message(self, message: QueueMessage) -> bool:
        """Return job to queue by removing .processing extension"""
        try:
            if os.path.exists(message.receipt_handle):
                original_path = message.receipt_handle.replace(".processing", "")
                os.rename(message.receipt_handle, original_path)
            return True
        except Exception:
            self.logger.exception("Error returning message")
            return False


class AzureStorageQueue(QueueInterface):
    """Azure Storage Queue implementation (works with Azurite)"""

    def __init__(
        self,
        connection_string: str,
        queue_name: str = "jobs",
        logger: logging.Logger = logging.getLogger("queue.AzureStorageQueue"),
    ):
        from azure.storage.queue import QueueServiceClient

        self.connection_string = connection_string
        self.queue_name = queue_name
        self.logger = logger
        self.queue_client = QueueServiceClient.from_connection_string(
            connection_string
        ).get_queue_client(queue_name)

        # Create queue if it doesn't exist
        try:
            self.queue_client.create_queue()
        except Exception:
            self.logger.debug("Queue likely already exists, skipping creation")

    def send_message(self, message: Dict[Any, Any]) -> bool:
        """Send message to Storage Queue"""
        try:
            self.queue_client.send_message(json.dumps(message))
            return True
        except Exception:
            self.logger.exception("Error sending message")
            return False

    def receive_message(self, visibility_timeout: int = 300) -> Optional[QueueMessage]:
        """Receive message from Storage Queue"""
        try:
            messages = self.queue_client.receive_messages(
                visibility_timeout=visibility_timeout, max_messages=1
            )
            for msg in messages:
                content = json.loads(msg.content)
                return QueueMessage(
                    id=msg.id, content=content, receipt_handle=(msg.id, msg.pop_receipt)
                )
        except Exception:
            self.logger.exception("Error receiving message")
        return None

    def delete_message(self, message: QueueMessage) -> bool:
        """Delete message from Storage Queue"""
        try:
            msg_id, pop_receipt = message.receipt_handle
            self.queue_client.delete_message(msg_id, pop_receipt)
            return True
        except Exception:
            self.logger.exception("Error deleting message")
            return False

    def return_message(self, message: QueueMessage) -> bool:
        """Update message visibility to 0 to return it"""
        try:
            msg_id, pop_receipt = message.receipt_handle
            self.queue_client.update_message(msg_id, pop_receipt, visibility_timeout=0)
            return True
        except Exception:
            self.logger.exception("Error returning message")
            return False
