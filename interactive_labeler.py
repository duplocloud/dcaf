import json
from services.cloudwatch_file_ingest import parse_cloudwatch_file
from pathlib import Path

def interactive_label(input_path: str, output_path: str):
    logs = parse_cloudwatch_file(input_path)
    for entry in logs:
        if entry.status == "FAILED":
            print("\nLOG:", entry.timestamp, entry.message)
            rc = input("  ↳ root_cause? ").strip()
            entry.root_cause = rc or "unspecified"
    # serialize Pydantic → dict → JSON
    data = [l.model_dump() for l in logs]
    Path(output_path).parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, default=str, indent=2)
    print(f"\nWrote labeled logs → {output_path}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("usage: python interactive_labeler.py sample_logs.txt data/labeled_logs.json")
        sys.exit(1)
    interactive_label(sys.argv[1], sys.argv[2])