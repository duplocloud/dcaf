from typing import List
import numpy as np
from sklearn.linear_model import LogisticRegression
from services.embedding import EmbeddingProvider
from schemas.cicd_log import CICDLogEntry

class FailurePredictor:
    """Train a lightweight classifier on CICDLogEntry embeddings."""
    def __init__(
        self,
        provider="bedrock",
        model_id="amazon.titan-embed-text-v1",
        region_name="us-east-1",
    ):
        self.embedder = EmbeddingProvider.create(
            provider=provider,
            model_id=model_id,
            region_name=region_name,
        )
        self.clf = LogisticRegression(class_weight="balanced", max_iter=200)

    def train(self, entries: List[CICDLogEntry]):
        # embed all messages
        texts = [e.message for e in entries]
        X = np.array(self.embedder.embed_documents(texts), dtype="float32")
        # labels: 1 for FAILED, 0 for SUCCEEDED
        y = np.array([1 if e.status=="FAILED" else 0 for e in entries])
        self.clf.fit(X, y)

    def predict_risk(self, text: str) -> float:
        emb = np.array(self.embedder.embed_query(text), dtype="float32").reshape(1, -1)
        return float(self.clf.predict_proba(emb)[0][1])
