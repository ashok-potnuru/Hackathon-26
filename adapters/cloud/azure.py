import base64
import json
import os

from adapters.cloud.base import CloudBase
from core.exceptions import AdapterError


class AzureCloudAdapter(CloudBase):
    def __init__(self):
        conn = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
        self._container = os.environ["AZURE_STORAGE_CONTAINER"]
        self._queue_name = os.environ["AZURE_QUEUE_NAME"]
        self._keyvault_url = os.environ.get("AZURE_KEYVAULT_URL", "")
        from azure.storage.blob import BlobServiceClient
        from azure.storage.queue import QueueClient
        self._blobs = BlobServiceClient.from_connection_string(conn)
        self._queue = QueueClient.from_connection_string(conn, self._queue_name)

    def store_file(self, key: str, data: bytes) -> None:
        self._blobs.get_container_client(self._container).upload_blob(name=key, data=data, overwrite=True)

    def read_file(self, key: str) -> bytes:
        return self._blobs.get_container_client(self._container).get_blob_client(key).download_blob().readall()

    def queue_job(self, payload: dict) -> str:
        msg = base64.b64encode(json.dumps(payload).encode()).decode()
        return self._queue.send_message(msg).id

    def dequeue_job(self) -> dict | None:
        for msg in self._queue.receive_messages(max_messages=1):
            body = json.loads(base64.b64decode(msg.content))
            body["_receipt_handle"] = f"{msg.id}:{msg.pop_receipt}"
            return body
        return None

    def delete_job(self, receipt_handle: str) -> None:
        try:
            message_id, pop_receipt = receipt_handle.split(":", 1)
            self._queue.delete_message(message_id, pop_receipt)
        except Exception:
            pass

    def get_secret(self, name: str) -> str:
        if not self._keyvault_url:
            return os.environ.get(name, "")
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        return SecretClient(vault_url=self._keyvault_url, credential=DefaultAzureCredential()).get_secret(name).value

    def health_check(self) -> None:
        try:
            self._blobs.get_container_client(self._container).get_container_properties()
        except Exception as e:
            raise AdapterError(f"Azure health check failed: {e}")
