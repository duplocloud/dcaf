# services/vector_store.py

import faiss
import numpy as np
from typing import List, Dict, Any

from services.embedding import EmbeddingProvider
from schemas.cicd_log import CICDLogEntry

class VectorStore:
    """
    A simple in-memory FAISS store for CICDLogEntry embeddings.
    """

    def __init__(
        self,
        provider: str = "bedrock",
        model_id: str = "amazon.titan-embed-text-v1",
        region_name: str = "us-east-1",
    ):
        # 1. Embedding client
        self.embedder = EmbeddingProvider.create(
            provider,
            model_id=model_id,
            region_name=region_name,
        )

        # 2. FAISS index + metadata store
        self.index: faiss.IndexFlatL2 | None = None
        self.metadata: List[CICDLogEntry] = []
        self.dim: int | None = None

    def upsert_entries(self, entries: List[CICDLogEntry]) -> None:
        """
        Embed each entry.message and add to the FAISS index.
        """
        texts = [e.message for e in entries]
        embs = self.embedder.embed_documents(texts)  # List[List[float]]
        arr = np.array(embs, dtype="float32")

        if self.index is None:
            self.dim = arr.shape[1]
            self.index = faiss.IndexFlatL2(self.dim)

        self.index.add(arr)
        self.metadata.extend(entries)

    def query(self, text: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Find top-k similar log entries for a new text.
        Returns a list of dicts with message, root_cause, status, and distance.
        """
        if self.index is None:
            return []

        # 1. Embed the incoming text
        emb = self.embedder.embed_query(text)
        arr = np.array([emb], dtype="float32")  # shape (1, dim)

        # 2. FAISS nearest-neighbor search
        distances, indices = self.index.search(arr, k)

        # 3. Gather and return metadata
        results: List[Dict[str, Any]] = []
        for dist, idx in zip(distances[0], indices[0]):
            entry = self.metadata[idx]
            results.append({
                "message":   entry.message,
                "root_cause": entry.root_cause,
                "status":    entry.status,
                "distance":  float(dist),
            })
        return results
