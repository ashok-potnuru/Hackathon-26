import asyncio
import time

from dotenv import load_dotenv
load_dotenv()

from config.registry import load_adapters
from core.observability.logger import get_logger
from core.pipeline import run_pipeline

logger = get_logger(__name__)


_MAX_RETRIES = 3
_retry_counts: dict[str, int] = {}


def run_worker() -> None:
    adapters = load_adapters()
    cloud = adapters["cloud"]
    notification = adapters["notification"]

    logger.info("Worker started — polling for jobs...")
    while True:
        job = cloud.dequeue_job()
        if not job:
            time.sleep(5)
            continue

        receipt = job.pop("_receipt_handle", None)
        issue_id = job.get("issue_id", "unknown")
        try:
            asyncio.run(run_pipeline(job, adapters))
            _retry_counts.pop(issue_id, None)
            if receipt:
                cloud.delete_job(receipt)
        except Exception as e:
            _retry_counts[issue_id] = _retry_counts.get(issue_id, 0) + 1
            attempt = _retry_counts[issue_id]
            logger.error(f"Pipeline failed for issue {issue_id} (attempt {attempt}/{_MAX_RETRIES}): {e}")
            if attempt >= _MAX_RETRIES:
                logger.error(f"Max retries reached for {issue_id} — dropping message")
                _retry_counts.pop(issue_id, None)
                if receipt:
                    cloud.delete_job(receipt)
            try:
                notification.send_alert("", f"AutoFix pipeline failed for issue {issue_id}: {e}")
            except Exception:
                pass


if __name__ == "__main__":
    run_worker()


def get_queue_depth() -> int:
    try:
        adapters = load_adapters()
        cloud = adapters["cloud"]
        if hasattr(cloud, "get_queue_depth"):
            return cloud.get_queue_depth()
    except Exception:
        pass
    return -1
