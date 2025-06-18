import json
from schemas.cicd_log import CICDLogEntry
from vector_store import VectorStore
import dotenv
dotenv.load_dotenv(override=True)

# 1. load your labeled logs
data = json.load(open("data/labeled_logs.json"))
entries = [CICDLogEntry.model_validate(d) for d in data]

# 2. build & populate FAISS
vs = VectorStore()
vs.upsert_entries(entries)
print("Indexed", len(entries), "entries")

# 3. test a query
new_log = "2024-06-01 10:03:10,999 [ERROR] Unit test suite hung after 30s"
for hit in vs.query(new_log, k=5):
    print(hit)
