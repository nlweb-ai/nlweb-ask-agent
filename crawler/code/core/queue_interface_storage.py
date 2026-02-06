"""
Azure Storage Queue with Azure AD Authentication
This version uses Workload Identity / Managed Identity instead of connection strings
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import log
from queue_interface import QueueInterface, QueueMessage

log.configure(os.environ)

_logger = logging.getLogger("queue.AzureStorageQueueAAD")


class AzureStorageQueueAAD(QueueInterface):
    """Azure Storage Queue implementation using Azure AD authentication"""

    def __init__(
        self,
        storage_account_name: str,
        queue_name: str = "crawler-jobs",
        logger: logging.Logger = logging.getLogger("queue.AzureStorageQueueAAD"),
    ):
        from azure.identity import DefaultAzureCredential
        from azure.storage.queue import QueueServiceClient

        self.storage_account_name = storage_account_name
        self.queue_name = queue_name
        self.account_url = f"https://{storage_account_name}.queue.core.windows.net"
        self.logger = logger

        # Use DefaultAzureCredential which automatically handles:
        # - Workload Identity (when AZURE_FEDERATED_TOKEN_FILE is set)
        # - Managed Identity (when running in Azure)
        # - Azure CLI (when running locally)
        self.credential = DefaultAzureCredential()

        # Create queue service client
        self.service_client = QueueServiceClient(
            account_url=self.account_url, credential=self.credential
        )
        self.queue_client = self.service_client.get_queue_client(queue_name)

    def send_message(self, message: Dict[str, Any]) -> bool:
        """Send message to Storage Queue"""
        try:
            content = json.dumps(message)
            self.queue_client.send_message(content)
            return True
        except Exception:
            self.logger.exception("Error sending message")
            return False

    def receive_message(self, visibility_timeout: int = 300) -> Optional[QueueMessage]:
        """Receive message from Storage Queue"""
        try:
            # Get messages (max 1)
            messages = self.queue_client.receive_messages(
                messages_per_page=1, visibility_timeout=visibility_timeout
            )

            for msg in messages:
                content = json.loads(msg.content)
                return QueueMessage(
                    id=msg.id,
                    content=content,
                    receipt_handle=msg,  # Store entire message for deletion
                )
        except Exception:
            self.logger.exception("Error receiving message")
        return None

    def delete_message(self, message: QueueMessage) -> bool:
        """Delete the message from Storage Queue"""
        try:
            msg = message.receipt_handle
            self.queue_client.delete_message(msg.id, msg.pop_receipt)
            return True
        except Exception:
            self.logger.exception("Error deleting message")
            return False

    def return_message(self, message: QueueMessage) -> bool:
        """Return message to queue by updating visibility timeout to 0"""
        try:
            msg = message.receipt_handle
            # Update visibility timeout to 0 to make message immediately available
            self.queue_client.update_message(
                msg.id, msg.pop_receipt, visibility_timeout=0
            )
            return True
        except Exception:
            self.logger.exception("Error returning message")
            return False

    def get_message_count(self) -> int:
        """Get approximate number of messages in queue"""
        try:
            properties = self.queue_client.get_queue_properties()
            return properties.approximate_message_count
        except Exception:
            self.logger.exception("Error getting message count")
            return -1


def ensure_queue_exists(storage_account_name: str, queue_name: str = "crawler-jobs"):
    """
    Ensure the Azure Storage Queue exists, creating it if necessary.
    This should be called once at application startup.
    """
    from azure.core.exceptions import ResourceExistsError
    from azure.identity import DefaultAzureCredential
    from azure.storage.queue import QueueServiceClient

    account_url = f"https://{storage_account_name}.queue.core.windows.net"
    credential = DefaultAzureCredential()
    service_client = QueueServiceClient(account_url=account_url, credential=credential)
    queue_client = service_client.get_queue_client(queue_name)

    try:
        queue_client.create_queue()
        _logger.info("Created queue %s", queue_name)
    except ResourceExistsError:
        _logger.info("Queue already exists: %s", queue_name)
    except Exception:
        _logger.exception("Error creating queue %s", queue_name)
        raise
