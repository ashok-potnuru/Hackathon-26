import json
import os
import re

import boto3

from adapters.cloud.base import CloudBase
from core.exceptions import AdapterError


class AWSAdapter(CloudBase):
    def __init__(self):
        region = os.environ.get("AWS_REGION", "us-east-1")
        self._bucket = os.environ["AWS_S3_BUCKET"]
        self._queue_url = os.environ["AWS_SQS_QUEUE_URL"]
        self._s3 = boto3.client("s3", region_name=region)
        self._sqs = boto3.client("sqs", region_name=region)
        self._secrets = boto3.client("secretsmanager", region_name=region)

    def store_file(self, key: str, data: bytes) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data)

    def read_file(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def queue_job(self, payload: dict) -> str:
        r = self._sqs.send_message(QueueUrl=self._queue_url, MessageBody=json.dumps(payload))
        return r["MessageId"]

    def dequeue_job(self) -> dict | None:
        r = self._sqs.receive_message(QueueUrl=self._queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=5)
        msgs = r.get("Messages", [])
        if not msgs:
            return None
        msg = msgs[0]
        try:
            body = json.loads(msg["Body"])
        except json.JSONDecodeError:
            clean = re.sub(r'[\x00-\x1f]', ' ', msg["Body"])
            body = json.loads(clean)
        body["_receipt_handle"] = msg["ReceiptHandle"]
        return body

    def delete_job(self, receipt_handle: str) -> None:
        self._sqs.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt_handle)

    def get_secret(self, name: str) -> str:
        return self._secrets.get_secret_value(SecretId=name).get("SecretString", "")

    def health_check(self) -> None:
        try:
            self._s3.head_bucket(Bucket=self._bucket)
        except Exception as e:
            raise AdapterError(f"AWS health check failed: {e}")
