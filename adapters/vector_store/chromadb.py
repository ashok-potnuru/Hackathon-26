import os

import chromadb

from adapters.vector_store.base import VectorStoreBase
from core.exceptions import AdapterError


class ChromaDBAdapter(VectorStoreBase):
    def __init__(self):
        host = os.environ.get("CHROMA_HOST", "localhost")
        port = int(os.environ.get("CHROMA_PORT", "8001"))
        self._client = chromadb.HttpClient(host=host, port=port)
        self._col = self._client.get_or_create_collection("fix_memory")

    def store_fix(self, issue_id: str, issue_text: str, fix_text: str) -> None:
        self._col.upsert(
            ids=[issue_id],
            documents=[issue_text],
            metadatas=[{"fix": fix_text, "issue_id": issue_id}],
        )

    def search_similar(self, issue_text: str, top_k: int = 5) -> list:
        count = self._col.count()
        if count == 0:
            return []
        results = self._col.query(query_texts=[issue_text], n_results=min(top_k, count))
        hits = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        for i, doc in enumerate(docs):
            hits.append({
                "issue": doc,
                "fix": metas[i].get("fix", "") if i < len(metas) else "",
                "distance": dists[i] if i < len(dists) else 0,
            })
        return hits

    def health_check(self) -> None:
        try:
            self._client.heartbeat()
        except Exception as e:
            raise AdapterError(f"ChromaDB health check failed: {e}")
