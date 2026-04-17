import hashlib
import os

from adapters.vector_store.base import VectorStoreBase
from core.exceptions import AdapterError


class PineconeAdapter(VectorStoreBase):
    def __init__(self):
        from pinecone import Pinecone
        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        self._index = pc.Index(os.environ.get("PINECONE_INDEX", "fix-memory"))

    def store_fix(self, issue_id: str, issue_text: str, fix_text: str) -> None:
        self._index.upsert(vectors=[{
            "id": issue_id,
            "values": self._embed(issue_text),
            "metadata": {"issue": issue_text, "fix": fix_text},
        }])

    def search_similar(self, issue_text: str, top_k: int = 5) -> list:
        results = self._index.query(vector=self._embed(issue_text), top_k=top_k, include_metadata=True)
        return [
            {"issue": m["metadata"].get("issue", ""), "fix": m["metadata"].get("fix", ""), "distance": m["score"]}
            for m in results.get("matches", [])
        ]

    def _embed(self, text: str) -> list:
        h = hashlib.sha256(text.encode()).digest()
        vec = [float(b) / 255.0 for b in h[:128]]
        return vec + [0.0] * (1536 - 128)

    def health_check(self) -> None:
        try:
            self._index.describe_index_stats()
        except Exception as e:
            raise AdapterError(f"Pinecone health check failed: {e}")
