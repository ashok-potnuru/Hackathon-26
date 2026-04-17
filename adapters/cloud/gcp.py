import base64
import json
import os

from adapters.cloud.base import CloudBase
from core.exceptions import AdapterError


class GCPAdapter(CloudBase):
    def __init__(self):
        self._project = os.environ["GCP_PROJECT"]
        self._bucket_name = os.environ["GCP_BUCKET"]
        self._topic = os.environ["GCP_PUBSUB_TOPIC"]
        self._subscription = os.environ["GCP_PUBSUB_SUBSCRIPTION"]
        from google.cloud import pubsub_v1, secretmanager, storage
        self._storage = storage.Client()
        self._publisher = pubsub_v1.PublisherClient()
        self._subscriber = pubsub_v1.SubscriberClient()
        self._secrets = secretmanager.SecretManagerServiceClient()

    def store_file(self, key: str, data: bytes) -> None:
        self._storage.bucket(self._bucket_name).blob(key).upload_from_string(data)

    def read_file(self, key: str) -> bytes:
        return self._storage.bucket(self._bucket_name).blob(key).download_as_bytes()

    def queue_job(self, payload: dict) -> str:
        data = base64.b64encode(json.dumps(payload).encode())
        return self._publisher.publish(self._topic, data=data).result()

    def dequeue_job(self) -> dict | None:
        resp = self._subscriber.pull(request={"subscription": self._subscription, "max_messages": 1})
        if not resp.received_messages:
            return None
        msg = resp.received_messages[0]
        body = json.loads(base64.b64decode(msg.message.data))
        body["_receipt_handle"] = msg.ack_id
        return body

    def delete_job(self, receipt_handle: str) -> None:
        self._subscriber.acknowledge(request={"subscription": self._subscription, "ack_ids": [receipt_handle]})

    def get_secret(self, name: str) -> str:
        resource = f"projects/{self._project}/secrets/{name}/versions/latest"
        return self._secrets.access_secret_version(request={"name": resource}).payload.data.decode()

    def health_check(self) -> None:
        try:
            self._storage.get_bucket(self._bucket_name)
        except Exception as e:
            raise AdapterError(f"GCP health check failed: {e}")
