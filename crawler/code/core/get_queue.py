import os

from queue_interface import QueueInterface


def get_queue() -> QueueInterface:
    """
    Factory function to get queue implementation with Azure AD support
    Supports: 'file' and 'storage' queue types
    """
    from queue_interface import FileQueue
    from queue_interface_storage import AzureStorageQueueAAD

    queue_type = os.getenv("QUEUE_TYPE", "file").lower()

    if queue_type == "file":
        return FileQueue(os.getenv("QUEUE_DIR", "queue"))

    elif queue_type == "storage":
        # Use AAD authentication for Storage Queue
        storage_account = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
        queue_name = os.getenv("AZURE_STORAGE_QUEUE_NAME", "crawler-jobs")

        if not storage_account:
            raise ValueError("AZURE_STORAGE_ACCOUNT_NAME environment variable not set")

        print(
            f"[Queue] Using Azure Storage Queue with AAD authentication: {storage_account}"
        )
        return AzureStorageQueueAAD(storage_account, queue_name)

    else:
        raise ValueError(
            f"Unknown queue type: {queue_type}. Supported types: 'file', 'storage'"
        )
